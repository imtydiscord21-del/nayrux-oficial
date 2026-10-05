"""
hardban.py — Hardban: un ban "duro". Si alguien desbanea al usuario (a mano, con
,unbanall, desde otro bot, etc.), este bot lo vuelve a banear al instante.

,hardban (alias ,hb) es un TOGGLE, igual que en Greed: si el usuario no está
hardbaneado, lo aplica. Si ya lo está, el mismo comando lo saca.

Comandos:
  ,hardban <@usuario|id> [razón]   — toggle: aplica o saca el hardban
  ,hb <@usuario|id> [razón]        — alias corto, lo mismo
  ,unhardban <@usuario|id>         — forma explícita de sacarlo (requiere Administrator)
  ,hardbanlist                     — lista de hardbans de este servidor

Los hardbans se guardan por servidor en la base de datos, así que sobreviven a
reinicios del bot. Al arrancar, el bot revisa que todos sigan baneados de
verdad (por si alguien los soltó mientras estaba caído).
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone
import asyncio
import logging

from config import db
from logger import send_log

log = logging.getLogger("antinuke.hardban")


def _get_hardbans(guild_id: int) -> dict:
    return db.get_guild(guild_id).get("hardbans", {})


def _save_hardbans(guild_id: int, hardbans: dict):
    config = db.get_guild(guild_id)
    config["hardbans"] = hardbans
    db.update_guild(guild_id, config)


def _err(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=0xed4245)


def _ok(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=0x57f287)


class Hardban(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        asyncio.create_task(self._startup_check())

    async def _startup_check(self):
        """Al arrancar, confirma que todos los hardbaneados sigan baneados de
        verdad — por si alguien los soltó mientras el bot estaba caído."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            hardbans = _get_hardbans(guild.id)
            for uid_str in list(hardbans.keys()):
                try:
                    await guild.fetch_ban(discord.Object(id=int(uid_str)))
                except discord.NotFound:
                    try:
                        await guild.ban(
                            discord.Object(id=int(uid_str)), delete_message_days=0,
                            reason="Hardban: re-aplicando tras reinicio del bot",
                        )
                        log.info(f"[{guild.name}] Re-hardbaneado {uid_str} tras reinicio")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                except (discord.Forbidden, discord.HTTPException):
                    pass

    # ── Listeners: lo que hace "duro" al ban ─────────────────────────────────

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        entry = _get_hardbans(guild.id).get(str(user.id))
        if not entry:
            return

        try:
            await guild.ban(
                user,
                reason=f"Hardban: reban automático ({entry.get('reason', 'sin razón')})",
                delete_message_days=0,
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"[{guild.name}] No pude rebanear a {user} ({user.id}): {e}")
            return

        unbanned_by = None
        try:
            async for log_entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if log_entry.target and log_entry.target.id == user.id:
                    unbanned_by = log_entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        extra = []
        if unbanned_by and unbanned_by.id != self.bot.user.id:
            extra.append(("Lo desbaneó", f"{unbanned_by.mention} `{unbanned_by}`", False))

        await send_log(
            guild,
            action="hardban",
            punishment="hardban",
            target=user,
            moderator=guild.me,
            reason="Alguien desbaneó a un usuario en hardban — reban automático",
            module="Hardban",
            category="mod",
            extra_fields=extra,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if str(member.id) not in _get_hardbans(member.guild.id):
            return
        try:
            await member.guild.ban(member, reason="Hardban: reingreso detectado", delete_message_days=0)
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning(f"[{member.guild.name}] No pude rebanear a {member} al reingresar: {e}")

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.command(name="hardban", aliases=["hb"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def hardban(self, ctx: commands.Context, user: discord.User, *, reason: str = "Sin razón"):
        hardbans = _get_hardbans(ctx.guild.id)

        # Toggle: si ya estaba hardbaneado, este mismo comando lo saca (igual que Greed)
        if str(user.id) in hardbans:
            hardbans.pop(str(user.id))
            _save_hardbans(ctx.guild.id, hardbans)
            try:
                await ctx.guild.unban(user, reason=f"Hardban removido por {ctx.author}")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                return await ctx.send(embed=_err("Lo saqué de la lista de hardban, pero Discord no me dejó desbanearlo."))
            return await ctx.send(embed=_ok(f"`{user}` (`{user.id}`) ya no está en hardban y fue desbaneado."))

        if user.id == ctx.author.id:
            return await ctx.send(embed=_err("No podés hardbanearte a vos mismo."))
        if user.id == self.bot.user.id:
            return await ctx.send(embed=_err("No me puedo hardbanear a mí mismo."))
        if user.id == ctx.guild.owner_id:
            return await ctx.send(embed=_err("No se puede hardbanear al dueño del servidor."))

        member = ctx.guild.get_member(user.id)
        if member:
            if ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
                return await ctx.send(embed=_err("No podés hardbanear a alguien con un rol igual o superior al tuyo."))
            if member.top_role >= ctx.guild.me.top_role:
                return await ctx.send(embed=_err("Ese usuario tiene un rol igual o superior al mío, no puedo banearlo."))

        reason = reason[:400]
        try:
            await ctx.guild.ban(user, reason=f"Hardban por {ctx.author}: {reason}", delete_message_days=0)
        except discord.Forbidden:
            return await ctx.send(embed=_err("Discord no me dejó banear a ese usuario (revisá mis permisos/jerarquía)."))
        except discord.HTTPException as e:
            return await ctx.send(embed=_err(f"Error al banear: {e}"))

        hardbans[str(user.id)] = {
            "reason": reason,
            "by": ctx.author.id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        _save_hardbans(ctx.guild.id, hardbans)

        await ctx.send(embed=_ok(
            f"`{user}` (`{user.id}`) quedó en **hardban**. Si alguien lo desbanea, lo vuelvo a banear solo.\n"
            f"Razón: {reason}\n"
            f"Usá `,hardban {user.id}` de nuevo (o `,hb {user.id}`) para sacarle el hardban."
        ))

    @commands.command(name="unhardban")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unhardban(self, ctx: commands.Context, user: discord.User):
        hardbans = _get_hardbans(ctx.guild.id)
        if str(user.id) not in hardbans:
            return await ctx.send(embed=_err(f"`{user}` no está en hardban."))

        hardbans.pop(str(user.id))
        _save_hardbans(ctx.guild.id, hardbans)

        try:
            await ctx.guild.unban(user, reason=f"Unhardban por {ctx.author}")
        except discord.NotFound:
            pass
        except discord.Forbidden:
            return await ctx.send(embed=_err("Lo saqué de la lista de hardban, pero Discord no me dejó desbanearlo."))

        await ctx.send(embed=_ok(f"`{user}` (`{user.id}`) ya no está en hardban y fue desbaneado."))

    @commands.command(name="hardbanlist", aliases=["hardbans"])
    @commands.has_permissions(ban_members=True)
    async def hardbanlist(self, ctx: commands.Context):
        hardbans = _get_hardbans(ctx.guild.id)
        if not hardbans:
            return await ctx.send(embed=discord.Embed(description="No hay hardbans en este servidor.", color=0x2b2d31))

        lines = []
        for i, (uid, entry) in enumerate(hardbans.items(), 1):
            when = discord.utils.format_dt(datetime.fromisoformat(entry["at"]), "R") if entry.get("at") else ""
            lines.append(f"`{i}.` <@{uid}> (`{uid}`) — {entry.get('reason', 'Sin razón')} {when}")

        shown = lines[:20]
        e = discord.Embed(title=f"Hardbans ({len(hardbans)})", description="\n".join(shown), color=0x2b2d31)
        if len(lines) > 20:
            e.set_footer(text=f"Mostrando 20 de {len(lines)}")
        await ctx.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Hardban(bot))
