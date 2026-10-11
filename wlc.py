"""
wlc.py — Mensaje de bienvenida (estilo de las capturas), con la sintaxis de aura_script.py.

  ,wlc config (canal) (mensaje)   — canal y mensaje de bienvenida
  ,wlc test                       — vista previa en el canal actual
  ,wlc variables                  — variables y etiquetas disponibles
  ,wlc templates                  — plantillas listas para copiar
  ,wlc reset                      — borra la configuración

Es independiente de ,welcome (welcome.py): si configuras los dos, se mandan los dos mensajes.
Configuración en el servidor: "wlc_config": {"channel_id": int, "message": str}
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
from ui import success, error
from webhook_utils import send_via_webhook

log = logging.getLogger("antinuke.wlc")


def _kwargs(content, embed, view) -> dict:
    return {k: v for k, v in (("content", content), ("embed", embed), ("view", view)) if v}


class Wlc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _config(self, guild_id: int):
        return db.get_guild(guild_id).get("wlc_config")

    @commands.group(name="wlc", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def wlc(self, ctx: commands.Context):
        e = info_embed(
            ctx, "bienvenida",
            ["configura el mensaje que se envía cuando alguien entra al servidor."],
            [("comandos", [
                "`,wlc config (canal) (mensaje)`",
                "`,wlc test`",
                "`,wlc variables`",
                "`,wlc templates`",
                "`,wlc reset`",
            ])],
        )
        await ctx.send(embed=e)

    @wlc.command(name="config")
    async def wlc_config(self, ctx: commands.Context, channel: discord.TextChannel = None, *, message: str = None):
        if channel is None or message is None:
            return await ctx.send(embed=config_usage_embed(
                ctx, cmd=",wlc config", base=",wlc", title="bienvenida - config",
                description=[
                    "define el canal de bienvenida y el formato del mensaje.",
                    "puedes usar embeds personalizados con `{embed:nombre}`",
                    "los botones se agregan con la etiqueta `{button: ...}`",
                ],
            ))
        problems = validate(message)
        if problems:
            return await error(ctx, "No pude guardar ese mensaje:\n" + "\n".join(f"• {p}" for p in problems))
        db.set_guild_field(ctx.guild.id, "wlc_config", {"channel_id": channel.id, "message": message})
        await success(ctx, f"El mensaje de bienvenida se enviará en {channel.mention}. Pruébalo con `,wlc test`.")

    @wlc.command(name="test")
    async def wlc_test(self, ctx: commands.Context):
        cfg = self._config(ctx.guild.id)
        if not cfg:
            return await error(ctx, "No hay un mensaje de bienvenida configurado. Usa `,wlc config`.")
        content, embed, view, problems = build_message(
            cfg["message"], ctx.author, ctx.guild, loader=lambda n: get_saved(ctx.guild.id, n)
        )
        if problems:
            return await error(ctx, "El mensaje tiene problemas:\n" + "\n".join(f"• {p}" for p in problems))
        if not (content or embed):
            return await error(ctx, "El mensaje quedó vacío.")
        await send_via_webhook(ctx.channel, **_kwargs(content, embed, view))

    @wlc.command(name="variables")
    async def wlc_variables(self, ctx: commands.Context):
        await ctx.send(embed=variables_embed(ctx, "wlc"))

    @wlc.command(name="templates")
    async def wlc_templates(self, ctx: commands.Context):
        await ctx.send(embed=templates_embed(ctx, "wlc"))

    @wlc.command(name="reset")
    async def wlc_reset(self, ctx: commands.Context):
        if not self._config(ctx.guild.id):
            return await error(ctx, "No hay un mensaje de bienvenida configurado.")
        db.set_guild_field(ctx.guild.id, "wlc_config", None)
        await success(ctx, "Se borró la configuración del mensaje de bienvenida.")

    # ── Evento ───────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        try:
            cfg = await asyncio.to_thread(self._config, member.guild.id)
            if not cfg:
                return
            channel = member.guild.get_channel(int(cfg["channel_id"]))
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(int(cfg["channel_id"]))
                except discord.HTTPException:
                    log.warning(f"[{member.guild.name}] El canal de bienvenida ya no existe; usa ,wlc config")
                    return
            content, embed, view, problems = await asyncio.to_thread(
                build_message, cfg["message"], member, member.guild,
                lambda n: get_saved(member.guild.id, n),
            )
            if problems:
                log.warning(f"[{member.guild.name}] Problemas en el mensaje de bienvenida: {problems}")
            if not (content or embed):
                return
            await send_via_webhook(channel, **_kwargs(content, embed, view))
            log.info(f"[{member.guild.name}] Bienvenida (wlc) enviada para {member}")
        except discord.Forbidden:
            log.warning(f"[{member.guild.name}] Sin permisos para mandar la bienvenida")
        except Exception:
            log.exception(f"[{member.guild.name}] Falló la bienvenida (wlc)")


async def setup(bot: commands.Bot):
    await bot.add_cog(Wlc(bot))
