"""
vanity_watch.py — Si un miembro pone el vanity del servidor (ej. "discord.gg/miserver"
o solo "miserver") en su ESTADO/actividad personalizada de Discord, le asigna
un rol de recompensa automáticamente y opcionalmente lo anuncia. Si lo saca,
le quita el rol.

Requiere el Intent de Presencias (Presence Intent) habilitado en el Developer
Portal de tu aplicación — sin eso, on_presence_update nunca dispara.

Comandos:
  ,vanity role <rol>            — rol que se da/quita
  ,vanity channel <#canal>      — canal para anunciar (opcional)
  ,vanity message <code $v{}>   — mensaje del anuncio (opcional, usa {user.mention} etc.)
  ,vanity status                — ver configuración actual
  ,vanity scan                  — revisa ahora mismo el estado de todos los miembros
                                   (útil justo después de configurar, o si el bot se reinició)
"""

import discord
from discord.ext import commands
from config import db
import logging
from webhook_utils import send_via_webhook
from embed_scripting import parse_code, validate_code, build_message

log = logging.getLogger("antinuke.vanity_watch")


def _custom_status_text(member: discord.Member) -> str:
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity):
            return (activity.name or "") + " " + (activity.state or "")
    return ""


def _has_vanity(member: discord.Member, vanity_code: str) -> bool:
    if not vanity_code:
        return False
    text = _custom_status_text(member).lower()
    return vanity_code.lower() in text


async def _grant(member: discord.Member, config: dict):
    role = member.guild.get_role(config.get("vanity_role_id"))
    if not role:
        return
    holders = set(config.get("vanity_holders", []))
    if member.id in holders:
        return  # ya lo tiene marcado, no repetir anuncio

    try:
        await member.add_roles(role, reason="Vanity detectado en el estado de Discord")
    except discord.Forbidden:
        return

    holders.add(member.id)
    config["vanity_holders"] = list(holders)
    db.update_guild(member.guild.id, config)

    channel_id = config.get("vanity_channel_id")
    message_code = config.get("vanity_message")
    if channel_id and message_code:
        channel = member.guild.get_channel(channel_id)
        if channel:
            parsed = parse_code(message_code)
            embed, content, view = build_message(parsed, member=member)
            try:
                kwargs = {}
                if content:
                    kwargs["content"] = content
                if embed:
                    kwargs["embed"] = embed
                if view:
                    kwargs["view"] = view
                await send_via_webhook(channel, **kwargs)
            except Exception as e:
                log.error(f"[{member.guild.name}] Vanity announce error: {e}")


async def _revoke(member: discord.Member, config: dict):
    holders = set(config.get("vanity_holders", []))
    if member.id not in holders:
        return
    role = member.guild.get_role(config.get("vanity_role_id"))
    if role:
        try:
            await member.remove_roles(role, reason="Ya no tiene el vanity en el estado de Discord")
        except discord.Forbidden:
            pass
    holders.discard(member.id)
    config["vanity_holders"] = list(holders)
    db.update_guild(member.guild.id, config)


class VanityWatch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        config = db.get_guild(after.guild.id)
        if not config.get("vanity_role_id"):
            return
        vanity_code = after.guild.vanity_url_code
        if not vanity_code:
            return

        if _has_vanity(after, vanity_code):
            await _grant(after, config)
        else:
            await _revoke(after, config)

    @commands.group(name="vanity", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def vanity(self, ctx: commands.Context):
        config = db.get_guild(ctx.guild.id)
        role = ctx.guild.get_role(config.get("vanity_role_id")) if config.get("vanity_role_id") else None
        channel = ctx.guild.get_channel(config.get("vanity_channel_id")) if config.get("vanity_channel_id") else None
        vanity_code = ctx.guild.vanity_url_code

        if not vanity_code:
            warn = "\n⚠️ Este servidor no tiene vanity URL configurado (hace falta cierto nivel de boost), así que esto no puede funcionar todavía."
        else:
            warn = f"\nVanity actual: `{vanity_code}`"

        e = discord.Embed(
            description=(
                f"**Rol:** {role.mention if role else 'sin configurar — usa `,vanity role <rol>`'}\n"
                f"**Canal de anuncio:** {channel.mention if channel else 'sin configurar (opcional)'}\n"
                f"**Mensaje:** {'configurado' if config.get('vanity_message') else 'sin configurar (opcional, sin esto no anuncia nada, solo da el rol)'}"
                f"{warn}"
            ),
            color=0x2b2d31,
        )
        await ctx.send(embed=e)

    @vanity.command(name="role")
    @commands.has_permissions(manage_guild=True)
    async def vanity_role(self, ctx: commands.Context, role: discord.Role):
        config = db.get_guild(ctx.guild.id)
        config["vanity_role_id"] = role.id
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(description=f"Rol de vanity configurado: {role.mention}", color=0x57f287))

    @vanity.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def vanity_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        config = db.get_guild(ctx.guild.id)
        config["vanity_channel_id"] = channel.id
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(description=f"Canal de anuncio configurado: {channel.mention}", color=0x57f287))

    @vanity.command(name="message")
    @commands.has_permissions(manage_guild=True)
    async def vanity_message(self, ctx: commands.Context, *, config_text: str):
        parsed_warnings = validate_code(config_text)
        config = db.get_guild(ctx.guild.id)
        config["vanity_message"] = config_text
        db.update_guild(ctx.guild.id, config)
        embed = discord.Embed(description="Mensaje de anuncio de vanity configurado.", color=0x57f287 if not parsed_warnings else 0xfee75c)
        if parsed_warnings:
            embed.add_field(name="Revisa esto", value="\n".join(f"• {w}" for w in parsed_warnings), inline=False)
        await ctx.send(embed=embed)

    @vanity.command(name="scan")
    @commands.has_permissions(manage_guild=True)
    async def vanity_scan(self, ctx: commands.Context):
        config = db.get_guild(ctx.guild.id)
        if not config.get("vanity_role_id"):
            return await ctx.send(embed=discord.Embed(description="Configurá primero `,vanity role <rol>`.", color=0xed4245))
        vanity_code = ctx.guild.vanity_url_code
        if not vanity_code:
            return await ctx.send(embed=discord.Embed(description="Este servidor no tiene vanity URL.", color=0xed4245))

        granted, revoked = 0, 0
        for member in ctx.guild.members:
            if member.bot:
                continue
            before_holders = set(config.get("vanity_holders", []))
            if _has_vanity(member, vanity_code):
                if member.id not in before_holders:
                    granted += 1
                await _grant(member, config)
            else:
                if member.id in before_holders:
                    revoked += 1
                await _revoke(member, config)
            config = db.get_guild(ctx.guild.id)  # refrescar tras cada cambio

        await ctx.send(embed=discord.Embed(
            description=f"Escaneo listo — `{granted}` roles nuevos otorgados, `{revoked}` quitados.",
            color=0x57f287,
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(VanityWatch(bot))
