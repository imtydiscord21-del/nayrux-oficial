"""
instagram.py — Notificaciones de Instagram (estilo bleed).

Comandos (permiso: manage_guild; también valen los permisos falsos):
  ,instagram add (canal) (usuario)                       — recibe las publicaciones de una cuenta   (alias: ,ig)
  ,instagram remove (canal) (usuario)                    — deja de recibirlas
  ,instagram message (usuario) (mensaje) [--pingable on|off]
                                                         — texto que acompaña cada notificación
  ,instagram list                                        — cuentas monitoreadas

Cómo funciona:
  Una tarea revisa cada INSTAGRAM_POLL_MINUTES (10 por defecto) las cuentas monitoreadas,
  UNA vez por cuenta aunque varios servidores la sigan, y manda las publicaciones nuevas
  a cada canal. La primera vez que se agrega una cuenta NO se manda lo que ya estaba publicado.

Variables de entorno (todas opcionales):
  INSTAGRAM_POLL_MINUTES  cada cuánto revisar (mínimo 5, por defecto 10)
  INSTAGRAM_SESSIONID     cookie "sessionid" de una cuenta de Instagram. Sin ella Instagram suele
                          bloquear las consultas desde servidores. Usa una cuenta secundaria.
  INSTAGRAM_PROXY         proxy (http://usuario:clave@host:puerto) si Instagram bloquea la IP del servidor.

IMPORTANTE: Instagram no tiene API pública para leer cuentas ajenas. Este módulo usa el mismo
endpoint que usa instagram.com para mostrar un perfil, y Instagram puede cambiarlo o bloquearlo
sin aviso. Si eso pasa, solo hay que cambiar InstagramClient.fetch_profile; todo lo demás sigue igual.
"""

import asyncio
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks

from config import db
from ui import success, warn, error, paginate
from webhook_utils import send_via_webhook

log = logging.getLogger("antinuke.instagram")

IG_APP_ID = "936619743392459"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

try:
    POLL_MINUTES = max(5, int(os.getenv("INSTAGRAM_POLL_MINUTES", "10")))
except ValueError:
    POLL_MINUTES = 10
SESSION_ID = os.getenv("INSTAGRAM_SESSIONID") or None
PROXY = os.getenv("INSTAGRAM_PROXY") or None

MAX_FEEDS_PER_GUILD = 10      # cuentas por servidor
MAX_NEW_PER_CHECK = 3         # nunca manda más de 3 publicaciones nuevas de golpe por cuenta
MAX_POST_AGE_HOURS = 48       # ignora publicaciones más viejas (p. ej. una fijada que reaparece)
SEEN_LIMIT = 40               # publicaciones recordadas por cuenta
BLOCK_BACKOFF_SECONDS = 15 * 60
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

INSTAGRAM_PINK = 0xE1306C


# ── Modelos y errores ────────────────────────────────────────────────────────

class IGNotFound(Exception):
    """La cuenta no existe."""


class IGBlocked(Exception):
    """Instagram rechazó la consulta (límite, login requerido, IP bloqueada...)."""


@dataclass
class IGPost:
    shortcode: str
    caption: str
    image_url: str | None
    is_video: bool
    timestamp: int
    carousel_count: int = 1

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/p/{self.shortcode}/"


@dataclass
class IGProfile:
    username: str
    full_name: str
    avatar_url: str | None
    is_private: bool
    posts: list = field(default_factory=list)  # más reciente primero

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/{self.username}/"


# ── Funciones puras (se prueban sin red) ─────────────────────────────────────

def clean_username(text: str) -> str | None:
    """'@user', 'https://www.instagram.com/user/?hl=es' o 'user' -> 'user' (None si no es válido)."""
    text = text.strip().strip("<>")
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", text, re.IGNORECASE)
    if m:
        text = m.group(1)
    text = text.lstrip("@").strip().lower()
    return text if USERNAME_RE.match(text) else None


def parse_profile(user: dict) -> IGProfile:
    """Convierte el JSON de web_profile_info en un IGProfile."""
    posts = []
    edges = ((user.get("edge_owner_to_timeline_media") or {}).get("edges")) or []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        shortcode = node.get("shortcode")
        if not shortcode:
            continue
        caption_edges = ((node.get("edge_media_to_caption") or {}).get("edges")) or []
        caption = ""
        if caption_edges:
            caption = (((caption_edges[0] or {}).get("node") or {}).get("text")) or ""
        children = ((node.get("edge_sidecar_to_children") or {}).get("edges")) or []
        posts.append(IGPost(
            shortcode=shortcode,
            caption=caption,
            image_url=node.get("display_url") or node.get("thumbnail_src"),
            is_video=bool(node.get("is_video")),
            timestamp=int(node.get("taken_at_timestamp") or 0),
            carousel_count=len(children) or 1,
        ))
    posts.sort(key=lambda p: p.timestamp, reverse=True)
    return IGProfile(
        username=user.get("username") or "",
        full_name=user.get("full_name") or "",
        avatar_url=user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
        is_private=bool(user.get("is_private")),
        posts=posts,
    )


def select_new_posts(profile: IGProfile, seen: list | None, now: float | None = None) -> list:
    """
    Publicaciones nuevas, de la más vieja a la más nueva.
    seen=None significa "primera vez que se ve esta cuenta": no se manda nada (solo se marca lo existente).
    """
    if seen is None:
        return []
    now = now if now is not None else time.time()
    fresh = [
        p for p in profile.posts
        if p.shortcode not in seen and (now - p.timestamp) <= MAX_POST_AGE_HOURS * 3600
    ]
    fresh.sort(key=lambda p: p.timestamp)
    return fresh[-MAX_NEW_PER_CHECK:]


def merge_seen(old: list | None, profile: IGProfile) -> list:
    """Lista actualizada de publicaciones ya vistas (las más recientes primero, con tope)."""
    merged = [p.shortcode for p in profile.posts]
    for sc in (old or []):
        if sc not in merged:
            merged.append(sc)
    return merged[:SEEN_LIMIT]


def parse_message_args(text: str):
    """'@everyone hola --pingable on' -> ('@everyone hola', True). Sin flag -> (texto, None)."""
    m = re.search(r"\s*--pingable\s+(on|off)\s*$", text, re.IGNORECASE)
    if not m:
        return text.strip(), None
    return text[:m.start()].strip(), m.group(1).lower() == "on"


def build_post_embed(profile: IGProfile, post: IGPost) -> discord.Embed:
    caption = post.caption.strip()
    if len(caption) > 1500:
        caption = caption[:1497] + "..."
    e = discord.Embed(description=caption or None, color=INSTAGRAM_PINK, url=post.url)
    e.set_author(name=f"@{profile.username}", url=profile.url, icon_url=profile.avatar_url)
    if post.image_url:
        e.set_image(url=post.image_url)
    kind = "Video" if post.is_video else ("Carrusel" if post.carousel_count > 1 else "Publicación")
    e.set_footer(text=f"Instagram • {kind}")
    if post.timestamp:
        e.timestamp = datetime.fromtimestamp(post.timestamp, tz=timezone.utc)
    return e


# ── Cliente de Instagram ─────────────────────────────────────────────────────

class InstagramClient:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self.blocked_until = 0.0

    def blocked(self) -> bool:
        return time.time() < self.blocked_until

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        return self._session

    async def fetch_profile(self, username: str) -> IGProfile:
        """Lee el perfil y sus últimas publicaciones. Lanza IGNotFound o IGBlocked."""
        if self.blocked():
            raise IGBlocked("Instagram está limitando las consultas; reintentando más tarde")

        async with self._lock:  # una consulta a la vez, con pausa entre ellas
            wait = 2.5 - (time.time() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait + random.random())
            self._last_request = time.time()

            session = await self._get_session()
            headers = {
                "User-Agent": USER_AGENT,
                "X-IG-App-ID": IG_APP_ID,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": f"https://www.instagram.com/{username}/",
            }
            cookies = {"sessionid": SESSION_ID} if SESSION_ID else None
            url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            try:
                async with session.get(url, headers=headers, cookies=cookies, proxy=PROXY) as resp:
                    if resp.status == 404:
                        raise IGNotFound(username)
                    if resp.status in (401, 403, 429):
                        self.blocked_until = time.time() + BLOCK_BACKOFF_SECONDS
                        raise IGBlocked(f"HTTP {resp.status}")
                    if resp.status != 200:
                        raise IGBlocked(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                raise IGBlocked(f"{type(e).__name__}: {e}")

        user = ((data or {}).get("data") or {}).get("user")
        if not user:
            # Respuesta vacía: o la cuenta no existe o Instagram pide iniciar sesión
            if (data or {}).get("require_login") or (data or {}).get("status") == "fail":
                self.blocked_until = time.time() + BLOCK_BACKOFF_SECONDS
                raise IGBlocked("Instagram pide iniciar sesión")
            raise IGNotFound(username)
        return parse_profile(user)


# ── Cog ──────────────────────────────────────────────────────────────────────

class Instagram(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = InstagramClient()

    async def cog_load(self):
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()
        await self.client.close()

    # ── Datos ────────────────────────────────────────────────────────────────

    def _feeds(self, guild_id: int) -> list:
        return list(db.get_guild(guild_id).get("instagram_feeds", []))

    def _save_feeds(self, guild_id: int, feeds: list):
        db.set_guild_field(guild_id, "instagram_feeds", feeds)

    @staticmethod
    def _state_key(username: str) -> str:
        return f"ig_seen:{username.lower()}"

    # ── Revisión periódica ───────────────────────────────────────────────────

    @tasks.loop(minutes=POLL_MINUTES)
    async def poll(self):
        try:
            await self._poll_once()
        except Exception:
            log.exception("Falló la revisión de Instagram")

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    async def _poll_once(self):
        subs = await asyncio.to_thread(db.guilds_with_field, "instagram_feeds")
        by_user: dict[str, list] = {}
        for guild_id, feeds in subs:
            for feed in feeds or []:
                by_user.setdefault(feed["username"].lower(), []).append((guild_id, feed))

        for username, targets in by_user.items():
            if self.client.blocked():
                log.warning("Instagram está limitando las consultas; se reintenta en la próxima ronda")
                return
            try:
                profile = await self.client.fetch_profile(username)
            except IGNotFound:
                log.warning(f"La cuenta de Instagram @{username} ya no existe o cambió de nombre")
                continue
            except IGBlocked as e:
                log.warning(f"Instagram bloqueó la consulta de @{username}: {e}")
                return

            state = await asyncio.to_thread(db.get, self._state_key(username), None)
            seen = (state or {}).get("seen") if state else None
            new_posts = select_new_posts(profile, seen)
            await asyncio.to_thread(db.set, self._state_key(username), {"seen": merge_seen(seen, profile)})

            for post in new_posts:
                for guild_id, feed in targets:
                    await self._dispatch(guild_id, feed, profile, post)

    async def _dispatch(self, guild_id: int, feed: dict, profile: IGProfile, post: IGPost):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(int(feed["channel_id"])) if guild else None
        if channel is None:
            return
        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="Ver en Instagram", url=post.url))
        mentions = discord.AllowedMentions.all() if feed.get("pingable") else discord.AllowedMentions.none()
        try:
            await send_via_webhook(
                channel,
                content=feed.get("message") or None,
                embed=build_post_embed(profile, post),
                view=view,
                allowed_mentions=mentions,
            )
        except Exception:
            log.exception(f"[{guild.name}] No se pudo enviar la notificación de @{profile.username}")

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.group(name="instagram", aliases=["ig"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def instagram(self, ctx: commands.Context):
        from cmd_help import build_command_card
        await ctx.send(embed=build_command_card(ctx))

    @instagram.command(name="add")
    async def ig_add(self, ctx: commands.Context, channel: discord.TextChannel, username: str):
        user = clean_username(username)
        if user is None:
            return await error(ctx, "Ese nombre de usuario de Instagram no es válido.")

        feeds = self._feeds(ctx.guild.id)
        if any(f["username"] == user and int(f["channel_id"]) == channel.id for f in feeds):
            return await warn(ctx, f"Ya recibes las publicaciones de **{user}** en {channel.mention}.")
        if len(feeds) >= MAX_FEEDS_PER_GUILD:
            return await error(ctx, f"Llegaste al límite de `{MAX_FEEDS_PER_GUILD}` cuentas de Instagram en este servidor.")

        async with ctx.typing():
            try:
                profile = await self.client.fetch_profile(user)
            except IGNotFound:
                return await error(ctx, f"No encontré ninguna cuenta de Instagram llamada **{user}**.")
            except IGBlocked as e:
                log.warning(f"No se pudo verificar @{user}: {e}")
                return await error(ctx, "Instagram no permitió la consulta en este momento. Inténtalo de nuevo más tarde.")

        if profile.is_private and not profile.posts:
            return await error(ctx, f"La cuenta **{user}** es privada, no puedo ver sus publicaciones.")

        # Si es la primera vez que se sigue esta cuenta, lo ya publicado se marca como visto
        key = self._state_key(user)
        state = await asyncio.to_thread(db.get, key, None)
        if not state:
            await asyncio.to_thread(db.set, key, {"seen": merge_seen(None, profile)})

        feeds.append({
            "username": user,
            "channel_id": channel.id,
            "message": None,
            "pingable": False,
        })
        self._save_feeds(ctx.guild.id, feeds)
        await success(ctx, f"Ahora recibirás las publicaciones de **{user}** en {channel.mention}.")

    @instagram.command(name="remove", aliases=["delete"])
    async def ig_remove(self, ctx: commands.Context, channel: discord.TextChannel, username: str):
        user = clean_username(username)
        feeds = self._feeds(ctx.guild.id)
        kept = [f for f in feeds if not (f["username"] == user and int(f["channel_id"]) == channel.id)]
        if user is None or len(kept) == len(feeds):
            return await error(ctx, f"No recibes las publicaciones de **{username.lstrip('@')}** en {channel.mention}.")
        self._save_feeds(ctx.guild.id, kept)
        await success(ctx, f"Ya no recibirás las publicaciones de **{user}** en {channel.mention}.")

    @instagram.command(name="message")
    async def ig_message(self, ctx: commands.Context, username: str, *, message: str):
        user = clean_username(username)
        text, pingable = parse_message_args(message)
        feeds = self._feeds(ctx.guild.id)
        mine = [f for f in feeds if f["username"] == user]
        if user is None or not mine:
            return await error(ctx, f"No recibes las publicaciones de **{username.lstrip('@')}**.")
        if not text:
            return await error(ctx, "Escribe el mensaje que quieres enviar con cada notificación.")
        for f in mine:
            f["message"] = text
            if pingable is not None:
                f["pingable"] = pingable
        self._save_feeds(ctx.guild.id, feeds)
        extra = ""
        if pingable is not None:
            extra = " Las menciones " + ("**sí**" if pingable else "**no**") + " notificarán."
        await success(ctx, f"Se actualizó el mensaje de **{user}**.{extra}")

    @instagram.command(name="list")
    async def ig_list(self, ctx: commands.Context):
        feeds = self._feeds(ctx.guild.id)
        if not feeds:
            return await error(ctx, "No hay cuentas de Instagram monitoreadas en este servidor.")
        lines = []
        for i, f in enumerate(feeds, start=1):
            ch = ctx.guild.get_channel(int(f["channel_id"]))
            where = ch.mention if ch else "`canal eliminado`"
            lines.append(f"`{i}` [**{f['username']}**](https://www.instagram.com/{f['username']}/) — {where}")
        icon = ctx.guild.icon.url if ctx.guild.icon else None
        await paginate(ctx, lines, title="Notificaciones de Instagram", icon_url=icon, per_page=10, noun="cuentas")

    # ── Mantenimiento ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Si borran el canal, se eliminan sus cuentas para no seguir consultando en vano."""
        try:
            feeds = await asyncio.to_thread(self._feeds, channel.guild.id)
            kept = [f for f in feeds if int(f["channel_id"]) != channel.id]
            if len(kept) != len(feeds):
                await asyncio.to_thread(self._save_feeds, channel.guild.id, kept)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Instagram(bot))
