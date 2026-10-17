"""
boostmsg.py — Mensajes de boost y unboost, y rol de recompensa (estilo de las capturas).

  ,boostmsg config (canal) (mensaje)        — mensaje cuando alguien boostea
  ,boostmsg unboostconfig (canal) (mensaje) — mensaje cuando alguien deja de boostear
  ,boostmsg test / testunboost              — vista previa en el canal actual
  ,boostmsg reward (rol)                    — rol que recibe quien boostea (se quita si deja de boostear)
  ,boostmsg removereward (rol)              — quita un rol de las recompensas
  ,boostmsg variables / templates           — ayuda
  ,boostmsg reset                           — borra todo

Es independiente de ,boost (boost.py): si configuras los dos, se mandan los dos mensajes.
Configuración: "boostmsg_config", "unboostmsg_config" ({"channel_id","message"}), "boost_rewards" ([role_id]).
"""

import asyncio
import logging

import discord
from discord.ext import commands

from config import db
from aura_script import build_message, validate
from aura_ui import info_embed
from msg_docs import variables_embed, templates_embed, config_usage_embed
from saved_embeds import get_saved
from ui import success, error, warn
from webhook_utils import send_via_webhook

log = logging.getLogger("antinuke.boostmsg")

MAX_REWARDS = 10


def _kwargs(content, embed, view) -> dict:
    return {k: v for k, v in (("content", content), ("embed", embed), ("view", view)) if v}


class BoostMsg(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get(self, guild_id: int, key: str):
        return db.get_guild(guild_id).get(key)

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.group(name="boostmsg", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def boostmsg(self, ctx: commands.Context):
        e = info_embed(
            ctx, "boostmsg",
            ["configura los mensajes de boost y unboost, y el rol de recompensa."],
            [("comandos", [
                "`,boostmsg config (canal) (mensaje)`",
                "`,boostmsg unboostconfig (canal) (mensaje)`",
                "`,boostmsg test`",
                "`,boostmsg testunboost`",
                "`,boostmsg reward (rol)`",
                "`,boostmsg removereward (rol)`",
                "`,boostmsg variables`",
                "`,boostmsg templates`",
                "`,boostmsg reset`",
            ])],
        )
        await ctx.send(embed=e)

    async def _save_config(self, ctx, key: str, label: str, channel, message, usage_cmd: str, title: str, desc: list):
        if channel is None or message is None:
            return await ctx.send(embed=config_usage_embed(
                ctx, cmd=usage_cmd, base=",boostmsg", title=title, description=desc,
                channel="#boosts", sample="gracias {user.mention} por boostear!",
            ))
        problems = validate(message)
        if problems:
            return await error(ctx, "No pude guardar ese mensaje:\n" + "\n".join(f"• {p}" for p in problems))
        db.set_guild_field(ctx.guild.id, key, {"channel_id": channel.id, "message": message})
        await success(ctx, f"El mensaje de {label} se enviará en {channel.mention}.")

    @boostmsg.command(name="config")
    async def bm_config(self, ctx: commands.Context, channel: discord.TextChannel = None, *, message: str = None):
        await self._save_config(
            ctx, "boostmsg_config", "boost", channel, message, ",boostmsg config", "boostmsg - config",
            ["define el canal y el mensaje que se envía cuando alguien boostea el servidor.",
             "puedes usar embeds personalizados con `{embed:nombre}`",
             "los botones se agregan con la etiqueta `{button: ...}`"],
        )

    @boostmsg.command(name="unboostconfig")
    async def bm_unboostconfig(self, ctx: commands.Context, channel: discord.TextChannel = None, *, message: str = None):
        await self._save_config(
            ctx, "unboostmsg_config", "unboost", channel, message, ",boostmsg unboostconfig", "boostmsg - unboostconfig",
            ["define el canal y el mensaje que se envía cuando alguien deja de boostear.",
             "puedes usar embeds personalizados con `{embed:nombre}`",
             "los botones se agregan con la etiqueta `{button: ...}`"],
        )

    async def _preview(self, ctx, key: str, hint: str):
        cfg = self._get(ctx.guild.id, key)
        if not cfg:
            return await error(ctx, f"No hay un mensaje configurado. Usa `{hint}`.")
        content, embed, view, problems = build_message(
            cfg["message"], ctx.author, ctx.guild,
            loader=lambda n: get_saved(ctx.guild.id, n), channel=ctx.channel,
            boost_count=await asyncio.to_thread(db.get_boost_count, ctx.guild.id, ctx.author.id),
        )
        if problems:
            return await error(ctx, "El mensaje tiene problemas:\n" + "\n".join(f"• {p}" for p in problems))
        if not (content or embed):
            return await error(ctx, "El mensaje quedó vacío.")
        await send_via_webhook(ctx.channel, **_kwargs(content, embed, view))

    @boostmsg.command(name="test")
    async def bm_test(self, ctx: commands.Context):
        await self._preview(ctx, "boostmsg_config", ",boostmsg config")

    @boostmsg.command(name="testunboost")
    async def bm_testunboost(self, ctx: commands.Context):
        await self._preview(ctx, "unboostmsg_config", ",boostmsg unboostconfig")

    @boostmsg.command(name="reward")
    async def bm_reward(self, ctx: commands.Context, role: discord.Role):
        if role.is_default() or role.managed:
            return await error(ctx, "Ese rol no se puede usar como recompensa.")
        if role >= ctx.guild.me.top_role:
            return await error(ctx, f"{role.mention} está por encima de mi rol más alto; no podría entregarlo.")
        rewards = list(self._get(ctx.guild.id, "boost_rewards") or [])
        if role.id in rewards:
            return await warn(ctx, f"{role.mention} ya es una recompensa de boost.")
        if len(rewards) >= MAX_REWARDS:
            return await error(ctx, f"Llegaste al límite de `{MAX_REWARDS}` roles de recompensa.")
        rewards.append(role.id)
        db.set_guild_field(ctx.guild.id, "boost_rewards", rewards)
        await success(ctx, f"Quien boostee el servidor recibirá {role.mention}.")

    @boostmsg.command(name="removereward")
    async def bm_removereward(self, ctx: commands.Context, role: discord.Role):
        rewards = list(self._get(ctx.guild.id, "boost_rewards") or [])
        if role.id not in rewards:
            return await error(ctx, f"{role.mention} no es una recompensa de boost.")
        rewards.remove(role.id)
        db.set_guild_field(ctx.guild.id, "boost_rewards", rewards)
        await success(ctx, f"{role.mention} ya no es una recompensa de boost.")

    @boostmsg.command(name="variables")
    async def bm_variables(self, ctx: commands.Context):
        await ctx.send(embed=variables_embed(ctx, "boost"))

    @boostmsg.command(name="templates")
    async def bm_templates(self, ctx: commands.Context):
        await ctx.send(embed=templates_embed(ctx, "boost"))

    @boostmsg.command(name="reset")
    async def bm_reset(self, ctx: commands.Context):
        keys = ("boostmsg_config", "unboostmsg_config", "boost_rewards")
        if not any(self._get(ctx.guild.id, k) for k in keys):
            return await error(ctx, "No hay nada configurado para borrar.")
        for k in keys:
            db.set_guild_field(ctx.guild.id, k, None)
        await success(ctx, "Se borró la configuración de boost (mensajes y recompensas).")

    # ── Evento ───────────────────────────────────────────────────────────────

    async def _send(self, member: discord.Member, key: str, boost_count=None):
        cfg = await asyncio.to_thread(self._get, member.guild.id, key)
        if not cfg:
            return
        channel = member.guild.get_channel(int(cfg["channel_id"]))
        if channel is None:
            log.warning(f"[{member.guild.name}] El canal de {key} ya no existe")
            return
        content, embed, view, problems = await asyncio.to_thread(
            build_message, cfg["message"], member, member.guild,
            lambda n: get_saved(member.guild.id, n),
            channel=channel, boost_count=boost_count,
        )
        if problems:
            log.warning(f"[{member.guild.name}] Problemas en {key}: {problems}")
        if content or embed:
            await send_via_webhook(channel, **_kwargs(content, embed, view))

    async def _rewards(self, member: discord.Member, give: bool):
        ids = await asyncio.to_thread(self._get, member.guild.id, "boost_rewards")
        roles = [r for r in (member.guild.get_role(i) for i in (ids or [])) if r is not None and r < member.guild.me.top_role]
        if not roles:
            return
        try:
            if give:
                await member.add_roles(*roles, reason="Recompensa por boostear el servidor")
            else:
                await member.remove_roles(*roles, reason="Dejó de boostear el servidor")
        except discord.HTTPException:
            log.warning(f"[{member.guild.name}] No pude actualizar los roles de recompensa de {member}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        boosted = before.premium_since is None and after.premium_since is not None
        unboosted = before.premium_since is not None and after.premium_since is None
        if not (boosted or unboosted):
            return
        try:
            boost_count = None
            if boosted:
                boost_count = await asyncio.to_thread(
                    db.record_boost_start, after.guild.id, after.id, after.premium_since
                )
            else:
                boost_count = await asyncio.to_thread(db.get_boost_count, after.guild.id, after.id)
            await self._send(
                after, "boostmsg_config" if boosted else "unboostmsg_config", boost_count
            )
            await self._rewards(after, give=boosted)
        except discord.Forbidden:
            log.warning(f"[{after.guild.name}] Sin permisos para el mensaje de boost")
        except Exception:
            log.exception(f"[{after.guild.name}] Falló el mensaje de boost")


async def setup(bot: commands.Bot):
    await bot.add_cog(BoostMsg(bot))
