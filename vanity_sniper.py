"""
vanity_sniper.py — Reclama sola una vanity (discord.gg/xxxx) para TU servidor en cuanto se libere.

Comandos (solo el dueño del servidor o del bot):
  ,vanityclaim add (código)       — empieza a vigilar esa vanity
  ,vanityclaim remove (código)    — deja de vigilarla
  ,vanityclaim list               — vanities vigiladas y estado del servidor
  ,vanityclaim channel (#canal)   — canal donde avisa al reclamar (por defecto el del sistema o un DM)
  ,vanityclaim check (código)     — revisa ahora mismo si está libre
  Alias del grupo: ,vsnipe

Cómo funciona:
  - Cada VANITY_POLL_SECONDS (30 por defecto, mínimo 10) pregunta a Discord si el código existe.
    Si Discord dice "invitación desconocida", el código está libre.
  - Entonces intenta ponerlo en el servidor (PATCH /guilds/{id}/vanity-url, el mismo endpoint que usa
    el panel de Discord) y avisa:  @dueño discord.gg/codigo
  - Si alguien se le adelanta o Discord lo rechaza, lo anota y sigue vigilando; tras 3 rechazos seguidos
    pausa ese código (puede estar reservado o bloqueado por Discord) y te avisa.

Requisitos:
  - El servidor debe tener la función de URL personalizada (nivel 3 de boosts o Partner).
  - El bot necesita el permiso "Administrar servidor" (o Administrador).
  - OJO: al reclamar una vanity nueva, la que tenías antes queda LIBRE para cualquiera.

Honestidad sobre las probabilidades: los nombres muy codiciados los toman en segundos bots hechos
para eso. Un chequeo cada 10-30 s funciona bien con nombres que se liberan poco a poco, pero no
puede competir contra ellos.

Configuración por servidor: "vanity_snipe": {"codes": ["codigo"], "channel_id": int|None}
"""

import asyncio
import logging
import os
import re
import time

import discord
from discord.ext import commands, tasks
from discord.http import Route

from config import db
from ui import success, error, warn, paginate

log = logging.getLogger("antinuke.vanity_sniper")

try:
    POLL_SECONDS = max(10, int(os.getenv("VANITY_POLL_SECONDS", "30")))
except ValueError:
    POLL_SECONDS = 30

MAX_CODES_PER_GUILD = 5
MAX_FAILED_CLAIMS = 3
CODE_RE = re.compile(r"^[a-z0-9-]{2,32}$")


# ── Lógica pura ──────────────────────────────────────────────────────────────

def clean_code(text: str):
    """'discord.gg/MiVanity', 'https://discord.gg/mivanity/' o 'MiVanity' -> 'mivanity' (None si no vale)."""
    text = text.strip().strip("<>").lower()
    m = re.search(r"(?:discord\.gg|discord\.com/invite|discordapp\.com/invite)/([a-z0-9-]+)", text)
    if m:
        text = m.group(1)
    return text if CODE_RE.match(text) else None


def claim_message(owner_id: int, code: str) -> str:
    """El aviso exacto: '@dueño discord.gg/codigo'."""
    return f"<@{owner_id}> discord.gg/{code}"


def _owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
            return True
        if await ctx.bot.is_owner(ctx.author):
            return True
        raise commands.CheckFailure("Solo el dueño del servidor puede usar este comando.")
    return commands.check(predicate)


class VanitySniper(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.failures: dict = {}      # (guild_id, code) -> rechazos seguidos
        self.last_check: dict = {}    # code -> timestamp de la última revisión

    async def cog_load(self):
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()

    # ── Datos ────────────────────────────────────────────────────────────────

    def _cfg(self, guild_id: int) -> dict:
        cfg = db.get_guild(guild_id).get("vanity_snipe") or {}
        return {"codes": list(cfg.get("codes", [])), "channel_id": cfg.get("channel_id")}

    def _save(self, guild_id: int, cfg: dict):
        db.set_guild_field(guild_id, "vanity_snipe", cfg)

    # ── Discord ──────────────────────────────────────────────────────────────

    async def is_available(self, code: str):
        """True = libre · False = ocupada · None = no se pudo saber (error de red, límite...)."""
        try:
            invite = await self.bot.fetch_invite(code, with_counts=False, with_expiration=False)
        except discord.NotFound:
            return True
        except discord.HTTPException as e:
            log.warning(f"No pude revisar la vanity '{code}': {e}")
            return None
        return False

    async def claim(self, guild: discord.Guild, code: str):
        """Pone la vanity en el servidor. Devuelve None si salió bien o el motivo del rechazo."""
        try:
            await self.bot.http.request(
                Route("PATCH", "/guilds/{guild_id}/vanity-url", guild_id=guild.id),
                json={"code": code},
                reason="Vanity reclamada automáticamente",
            )
            return None
        except discord.HTTPException as e:
            return f"{e.status}: {e.text or e}"
        except Exception as e:
            return str(e)

    async def _notify(self, guild: discord.Guild, text: str = None, embed: discord.Embed = None):
        """Avisa en el canal elegido, si no en el canal del sistema, y si no por DM al dueño."""
        cfg = self._cfg(guild.id)
        channel = guild.get_channel(int(cfg["channel_id"])) if cfg.get("channel_id") else None
        channel = channel or guild.system_channel
        mentions = discord.AllowedMentions(users=True, roles=False, everyone=False)
        if channel is not None:
            try:
                await channel.send(content=text, embed=embed, allowed_mentions=mentions)
                return True
            except discord.HTTPException:
                pass
        try:
            owner = guild.owner or await self.bot.fetch_user(guild.owner_id)
            await owner.send(content=text, embed=embed)
            return True
        except Exception:
            log.warning(f"[{guild.name}] No pude avisar a nadie sobre la vanity")
            return False

    # ── Revisión periódica ───────────────────────────────────────────────────

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll(self):
        try:
            await self._poll_once()
        except Exception:
            log.exception("Falló la revisión de vanities")

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    async def _poll_once(self):
        rows = await asyncio.to_thread(db.guilds_with_field, "vanity_snipe")
        by_code: dict = {}
        for guild_id, cfg in rows:
            for code in (cfg or {}).get("codes", []):
                by_code.setdefault(code, []).append(guild_id)

        for code, guild_ids in by_code.items():
            available = await self.is_available(code)
            self.last_check[code] = time.time()
            if available is not True:
                continue
            for guild_id in guild_ids:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue
                if await self._try_claim(guild, code):
                    break          # otro servidor ya no puede tenerla
            await asyncio.sleep(0.5)

    async def _try_claim(self, guild: discord.Guild, code: str) -> bool:
        """Intenta reclamar. Devuelve True si se logró."""
        if "VANITY_URL" not in guild.features:
            await self._drop(guild, code)
            await self._notify(guild, embed=self._embed(
                f"No pude reclamar **discord.gg/{code}**: este servidor no tiene la función de URL personalizada "
                f"(necesita nivel 3 de boosts o ser Partner). Dejé de vigilar ese código.", 0xED4245))
            return False

        reason = await self.claim(guild, code)
        key = (guild.id, code)
        if reason is None:
            self.failures.pop(key, None)
            await self._drop(guild, code)
            log.info(f"[{guild.name}] Vanity reclamada: {code}")
            await self._notify(
                guild, text=claim_message(guild.owner_id, code),
                embed=self._embed(f"Reclamé **discord.gg/{code}** para este servidor.", 0x57F287),
            )
            return True

        self.failures[key] = self.failures.get(key, 0) + 1
        log.warning(f"[{guild.name}] Discord rechazó la vanity '{code}' ({self.failures[key]}/{MAX_FAILED_CLAIMS}): {reason}")
        if self.failures[key] >= MAX_FAILED_CLAIMS:
            self.failures.pop(key, None)
            await self._drop(guild, code)
            await self._notify(guild, embed=self._embed(
                f"Discord rechazó **discord.gg/{code}** {MAX_FAILED_CLAIMS} veces seguidas, así que dejé de vigilarla "
                f"(puede estar reservada o bloqueada).\nMotivo: `{reason[:300]}`", 0xFEE75C))
        return False

    async def _drop(self, guild: discord.Guild, code: str):
        cfg = self._cfg(guild.id)
        if code in cfg["codes"]:
            cfg["codes"].remove(code)
            await asyncio.to_thread(self._save, guild.id, cfg)

    @staticmethod
    def _embed(text: str, color: int) -> discord.Embed:
        return discord.Embed(description=text, color=color)

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.group(name="vanityclaim", aliases=["vsnipe"], invoke_without_command=True)
    @_owner_only()
    async def vanityclaim(self, ctx: commands.Context):
        from cmd_help import build_command_card
        await ctx.send(embed=build_command_card(ctx))

    @vanityclaim.command(name="add")
    async def vc_add(self, ctx: commands.Context, code: str):
        code = clean_code(code)
        if code is None:
            return await error(ctx, "Ese código no es válido. Usa solo letras, números y guiones (2 a 32 caracteres).")
        if "VANITY_URL" not in ctx.guild.features:
            return await error(ctx, "Este servidor no tiene la función de URL personalizada, así que no podría ponerla. "
                                    "Necesita nivel 3 de boosts o ser Partner.")
        if ctx.guild.vanity_url_code and ctx.guild.vanity_url_code.lower() == code:
            return await warn(ctx, f"**discord.gg/{code}** ya es la vanity de este servidor.")

        cfg = self._cfg(ctx.guild.id)
        if code in cfg["codes"]:
            return await warn(ctx, f"Ya estoy vigilando **discord.gg/{code}**.")
        if len(cfg["codes"]) >= MAX_CODES_PER_GUILD:
            return await error(ctx, f"Llegaste al límite de `{MAX_CODES_PER_GUILD}` vanities vigiladas.")

        available = await self.is_available(code)
        cfg["codes"].append(code)
        self._save(ctx.guild.id, cfg)

        note = ""
        if ctx.guild.vanity_url_code:
            note = f"\nAl reclamarla, tu vanity actual (**discord.gg/{ctx.guild.vanity_url_code}**) quedará libre para cualquiera."
        if available is True:
            note += "\nAhora mismo parece estar libre; lo intentaré en la próxima revisión."
        await success(ctx, f"Vigilaré **discord.gg/{code}** cada `{POLL_SECONDS}` segundos y la pondré sola en cuanto se libere.{note}")

    @vanityclaim.command(name="remove", aliases=["delete"])
    async def vc_remove(self, ctx: commands.Context, code: str):
        code = clean_code(code)
        cfg = self._cfg(ctx.guild.id)
        if code is None or code not in cfg["codes"]:
            return await error(ctx, "No estoy vigilando esa vanity.")
        cfg["codes"].remove(code)
        self._save(ctx.guild.id, cfg)
        self.failures.pop((ctx.guild.id, code), None)
        await success(ctx, f"Dejé de vigilar **discord.gg/{code}**.")

    @vanityclaim.command(name="list")
    async def vc_list(self, ctx: commands.Context):
        cfg = self._cfg(ctx.guild.id)
        if not cfg["codes"]:
            return await error(ctx, "No hay vanities vigiladas en este servidor.")
        lines = []
        for i, code in enumerate(cfg["codes"], start=1):
            seen = self.last_check.get(code)
            when = f"<t:{int(seen)}:R>" if seen else "aún no revisada"
            lines.append(f"`{i}` **discord.gg/{code}** — {when}")
        icon = ctx.guild.icon.url if ctx.guild.icon else None
        await paginate(ctx, lines, title="Vanities vigiladas", icon_url=icon, per_page=10, noun="vanities")

    @vanityclaim.command(name="channel")
    async def vc_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        cfg = self._cfg(ctx.guild.id)
        cfg["channel_id"] = channel.id
        self._save(ctx.guild.id, cfg)
        await success(ctx, f"Avisaré en {channel.mention} cuando reclame una vanity.")

    @vanityclaim.command(name="check")
    async def vc_check(self, ctx: commands.Context, code: str):
        code = clean_code(code)
        if code is None:
            return await error(ctx, "Ese código no es válido.")
        async with ctx.typing():
            available = await self.is_available(code)
        if available is None:
            return await error(ctx, "No pude consultarlo en este momento. Inténtalo de nuevo en un rato.")
        if available:
            return await success(ctx, f"**discord.gg/{code}** parece estar **libre**.")
        await warn(ctx, f"**discord.gg/{code}** está **ocupada**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(VanitySniper(bot))
