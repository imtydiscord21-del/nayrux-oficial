"""
premium.py — Comandos "Premium": solo el dueño del bot (OWNER_IDS) o el dueño
del servidor donde se ejecuta el comando pueden usarlos.

PERFIL DEL BOT POR SERVIDOR (no afecta a otros servidores ni al perfil global):
  ,changeavatar [url]   — avatar del bot en ESTE servidor (también acepta una imagen adjunta)
  ,changename <nombre>  — nombre del bot en ESTE servidor
  ,changebanner [url]   — banner del bot en ESTE servidor (si Discord lo permite)
  ,resetprofile         — quita la personalización de ESTE servidor

Cómo funciona (para que siempre se note el cambio):
  1. El nombre y el avatar se guardan en la base de datos para este servidor y los
     mensajes del bot (que salen por webhook, ver webhook_utils.py) usan ese nombre y
     avatar. Esto no depende de ningún permiso especial de Discord.
  2. Además se intenta cambiar el perfil nativo del bot en este servidor (apodo, avatar
     y banner por servidor) para que también se vea así en la lista de miembros.

PERFIL GLOBAL (cambia el bot en TODOS los servidores — solo OWNER_IDS):
  ,globalavatar [url]  ,globalname <nombre>  ,globalbanner [url]  ,globalreset

Nota: Discord no permite editar la "bio"/descripción de una app vía el token
del bot (solo desde el Developer Portal), así que no existe ,changebio aquí.
"""

import base64
import io

import aiohttp
import discord
from discord.ext import commands
from discord.http import Route

from config import db
from webhook_utils import forget_guild_webhooks

GREEN = 0x57F287
RED = 0xED4245

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024      # límite de lo que se descarga
MAX_GIF_BYTES = 3 * 1024 * 1024           # un GIF animado se guarda tal cual si pesa menos que esto


def is_bot_or_guild_owner():
    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
            return True
        raise commands.CheckFailure("Este comando es solo para el dueño del bot o el dueño del servidor.")
    return commands.check(predicate)


# ── Imágenes ─────────────────────────────────────────────────────────────────

async def _fetch_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise ValueError(f"No pude descargar esa imagen (HTTP {resp.status}).")
            data = await resp.content.read(MAX_DOWNLOAD_BYTES + 1)
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise ValueError("La imagen pesa demasiado (máximo 8 MB).")
            return data


async def _get_image_bytes(ctx: commands.Context, url: str | None) -> bytes:
    """Imagen desde un adjunto del mensaje o desde una URL."""
    if ctx.message.attachments:
        att = ctx.message.attachments[0]
        if att.size > MAX_DOWNLOAD_BYTES:
            raise ValueError("La imagen pesa demasiado (máximo 8 MB).")
        return await att.read()
    if not url:
        raise ValueError("Pasa una URL de imagen o adjunta la imagen al mensaje.")
    return await _fetch_bytes(url.strip("<>"))


def _process_avatar(data: bytes) -> bytes:
    """Valida que sea una imagen y la deja en un tamaño razonable. Un GIF animado
    se conserva tal cual (si no es muy pesado); lo demás se guarda como PNG ≤ 512px."""
    try:
        from PIL import Image
    except ImportError:  # sin Pillow se acepta tal cual si no es enorme
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("La imagen pesa demasiado (máximo 2 MB).")
        return data

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("Ese archivo no parece una imagen válida (usa PNG, JPG, GIF o WEBP).")

    if getattr(img, "is_animated", False) and img.format == "GIF":
        if len(data) > MAX_GIF_BYTES:
            raise ValueError("Ese GIF pesa demasiado (máximo 3 MB).")
        return data

    img = img.convert("RGBA")
    img.thumbnail((512, 512))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _data_uri(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
    elif data.startswith(b"GIF8"):
        mime = "image/gif"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


# ── Perfil nativo del bot en un servidor (best effort) ───────────────────────

async def _edit_member_profile(bot: commands.Bot, guild: discord.Guild, payload: dict, reason: str) -> str | None:
    """
    Cambia el perfil del bot SOLO en este servidor (apodo / avatar / banner por servidor)
    con PATCH /guilds/{id}/members/@me. Devuelve None si salió bien, o el motivo del error.
    Nunca lanza: si Discord lo rechaza, los mensajes del bot igual usan la persona guardada.
    """
    try:
        await bot.http.request(
            Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild.id),
            json=payload,
            reason=reason,
        )
        return None
    except discord.HTTPException as e:
        return str(e.text or e)
    except Exception as e:  # versión de discord.py distinta, etc.
        return str(e)


def _embed(description: str, color: int = GREEN) -> discord.Embed:
    return discord.Embed(description=description, color=color)


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Perfil del bot EN ESTE SERVIDOR ──────────────────────────────────────

    @commands.command(name="changeavatar")
    @commands.guild_only()
    @is_bot_or_guild_owner()
    async def changeavatar(self, ctx: commands.Context, url: str = None):
        try:
            raw = await _get_image_bytes(ctx, url)
            data = _process_avatar(raw)
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        except Exception as e:
            return await ctx.send(embed=_embed(f"No pude leer esa imagen: {e}", RED))

        # 1) Persona guardada: los mensajes del bot en este servidor usan esta imagen
        db.set_persona(ctx.guild.id, avatar=data)
        forget_guild_webhooks(ctx.guild)

        # 2) Perfil nativo del bot en este servidor (lista de miembros, etc.)
        err = await _edit_member_profile(
            self.bot, ctx.guild, {"avatar": _data_uri(data)}, f"Avatar del bot cambiado por {ctx.author}"
        )

        desc = "Avatar del bot actualizado **solo en este servidor**."
        if err:
            desc += (
                "\nLos mensajes del bot ya usan la nueva imagen, pero Discord no dejó cambiar "
                "el perfil nativo del bot en la lista de miembros."
            )
        await ctx.send(embed=_embed(desc))

    @commands.command(name="changebanner")
    @commands.guild_only()
    @is_bot_or_guild_owner()
    async def changebanner(self, ctx: commands.Context, url: str = None):
        try:
            raw = await _get_image_bytes(ctx, url)
            data = _process_avatar(raw)
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        except Exception as e:
            return await ctx.send(embed=_embed(f"No pude leer esa imagen: {e}", RED))

        err = await _edit_member_profile(
            self.bot, ctx.guild, {"banner": _data_uri(data)}, f"Banner del bot cambiado por {ctx.author}"
        )
        if err:
            return await ctx.send(embed=_embed(f"Discord rechazó el banner por servidor: {err}", RED))
        await ctx.send(embed=_embed("Banner del bot actualizado **solo en este servidor**."))

    @commands.command(name="changename")
    @commands.guild_only()
    @is_bot_or_guild_owner()
    async def changename(self, ctx: commands.Context, *, name: str):
        name = name.strip()
        if len(name) < 2 or len(name) > 32:
            return await ctx.send(embed=_embed("El nombre debe tener entre 2 y 32 caracteres.", RED))
        lowered = name.lower()
        if "discord" in lowered or "clyde" in lowered:
            return await ctx.send(embed=_embed(
                "Discord no acepta nombres de webhook que contengan «discord» o «clyde». Prueba con otro nombre.", RED
            ))

        # 1) Persona guardada: los mensajes del bot en este servidor salen con este nombre
        db.set_persona(ctx.guild.id, name=name)

        # 2) Apodo del bot en este servidor (no toca el nombre global)
        err = await _edit_member_profile(self.bot, ctx.guild, {"nick": name}, f"Nombre del bot cambiado por {ctx.author}")
        if err:
            try:
                await ctx.guild.me.edit(nick=name, reason=f"Nombre del bot cambiado por {ctx.author}")
                err = None
            except discord.HTTPException as e:
                err = str(e)

        desc = f"Nombre del bot cambiado a **{name}** **solo en este servidor**."
        if err:
            desc += "\nLos mensajes del bot ya salen con ese nombre, pero no pude cambiar su apodo en la lista de miembros (revisa que tenga el permiso «Cambiar apodo»)."
        await ctx.send(embed=_embed(desc))

    @commands.command(name="resetprofile")
    @commands.guild_only()
    @is_bot_or_guild_owner()
    async def resetprofile(self, ctx: commands.Context):
        db.clear_persona(ctx.guild.id)
        forget_guild_webhooks(ctx.guild)
        # apodo, avatar y banner por servidor vuelven a ser los del perfil global
        err = await _edit_member_profile(
            self.bot, ctx.guild, {"nick": None, "avatar": None, "banner": None},
            f"Perfil del bot restablecido por {ctx.author}",
        )
        if err:
            try:
                await ctx.guild.me.edit(nick=None, reason=f"Perfil del bot restablecido por {ctx.author}")
            except discord.HTTPException:
                pass
        await ctx.send(embed=_embed("Nombre, avatar y banner del bot restablecidos en este servidor."))

    # ── Perfil GLOBAL del bot (todos los servidores) — solo OWNER_IDS ────────

    @commands.command(name="globalavatar")
    @commands.is_owner()
    async def globalavatar(self, ctx: commands.Context, url: str = None):
        try:
            data = _process_avatar(await _get_image_bytes(ctx, url))
            await self.bot.user.edit(avatar=data)
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(f"Discord rechazó la imagen: {e}", RED))
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        await ctx.send(embed=_embed("Avatar **global** del bot actualizado (todos los servidores)."))

    @commands.command(name="globalbanner")
    @commands.is_owner()
    async def globalbanner(self, ctx: commands.Context, url: str = None):
        try:
            data = _process_avatar(await _get_image_bytes(ctx, url))
            await self.bot.user.edit(banner=data)
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(f"Discord rechazó la imagen: {e}", RED))
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        await ctx.send(embed=_embed("Banner **global** del bot actualizado (todos los servidores)."))

    @commands.command(name="globalname")
    @commands.is_owner()
    async def globalname(self, ctx: commands.Context, *, name: str):
        if len(name) < 2 or len(name) > 32:
            return await ctx.send(embed=_embed("El nombre debe tener entre 2 y 32 caracteres.", RED))
        try:
            await self.bot.user.edit(username=name)
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(
                f"Discord rechazó el cambio (probablemente el límite de 2 cambios de nombre por hora): {e}", RED
            ))
        await ctx.send(embed=_embed(f"Nombre **global** del bot cambiado a **{name}** (todos los servidores)."))

    @commands.command(name="globalreset")
    @commands.is_owner()
    async def globalreset(self, ctx: commands.Context):
        try:
            await self.bot.user.edit(avatar=None, banner=None)
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(f"Discord rechazó el cambio: {e}", RED))
        await ctx.send(embed=_embed("Avatar y banner **globales** del bot restablecidos."))

    # ── Perfil del servidor ──────────────────────────────────────────────────

    @commands.command(name="guildicon")
    @is_bot_or_guild_owner()
    async def guildicon(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await ctx.guild.edit(icon=data, reason=f"Cambiado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(f"Discord rechazó la imagen: {e}", RED))
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        await ctx.send(embed=_embed("Ícono del servidor actualizado."))

    @commands.command(name="guildbanner")
    @is_bot_or_guild_owner()
    async def guildbanner(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await ctx.guild.edit(banner=data, reason=f"Cambiado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=_embed(
                f"Discord rechazó la imagen (el server necesita nivel de boost para esto): {e}", RED
            ))
        except ValueError as e:
            return await ctx.send(embed=_embed(str(e), RED))
        await ctx.send(embed=_embed("Banner del servidor actualizado."))

    # ── Utilidad ─────────────────────────────────────────────────────────────

    @commands.command(name="selfpurge")
    @is_bot_or_guild_owner()
    async def selfpurge(self, ctx: commands.Context, amount: int = 25):
        amount = max(1, min(amount, 200))
        deleted = await ctx.channel.purge(
            limit=200,
            check=lambda m: m.author.id == ctx.author.id,
            bulk=True,
        )
        deleted = deleted[:amount]
        msg = await ctx.send(embed=_embed(f"Borré `{len(deleted)}` de tus mensajes."))
        await msg.delete(delay=4)


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
