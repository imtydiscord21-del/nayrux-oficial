"""
info_extra.py — Comandos de información que faltaban:
  ,emojiinfo (emoji)   — datos de un emoji personalizado
  ,stickerinfo         — datos de un sticker (mándalo en el mensaje o responde a uno)
  ,stats               — estadísticas del bot
"""

import platform
import time

import discord
from discord.ext import commands

from aura_ui import COLOR, info_embed, duration_es
from ui import error

_STARTED = time.time()


class InfoExtra(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="emojiinfo", aliases=["ei"])
    async def emojiinfo(self, ctx: commands.Context, emoji: discord.PartialEmoji):
        if emoji.id is None:
            return await error(ctx, "Ese es un emoji normal; usa un emoji personalizado de un servidor.")
        known = self.bot.get_emoji(emoji.id)
        lines = [
            f"**Nombre:** `{emoji.name}`",
            f"**ID:** `{emoji.id}`",
            f"**Animado:** {'sí' if emoji.animated else 'no'}",
            f"**Creado:** {discord.utils.format_dt(emoji.created_at, 'F')}",
        ]
        if known is not None and known.guild is not None:
            lines.append(f"**Servidor:** {known.guild.name}")
        lines.append(f"**Enlace:** [abrir imagen]({emoji.url})")
        e = info_embed(ctx, "Información del emoji", lines)
        e.set_thumbnail(url=emoji.url)
        await ctx.send(embed=e)

    @commands.command(name="stickerinfo", aliases=["si"])
    async def stickerinfo(self, ctx: commands.Context):
        items = list(ctx.message.stickers)
        ref = ctx.message.reference
        if not items and ref is not None and isinstance(ref.resolved, discord.Message):
            items = list(ref.resolved.stickers)
        if not items:
            return await error(ctx, "Envía un sticker con el comando o responde a un mensaje que tenga uno.")
        try:
            sticker = await items[0].fetch()
        except discord.HTTPException:
            return await error(ctx, "No pude obtener la información de ese sticker.")
        lines = [
            f"**Nombre:** `{sticker.name}`",
            f"**ID:** `{sticker.id}`",
            f"**Formato:** `{sticker.format.name}`",
            f"**Creado:** {discord.utils.format_dt(sticker.created_at, 'F')}",
        ]
        description = getattr(sticker, "description", None)
        if description:
            lines.append(f"**Descripción:** {description}")
        guild = getattr(sticker, "guild", None)
        if guild is not None:
            lines.append(f"**Servidor:** {guild.name}")
        lines.append(f"**Enlace:** [abrir imagen]({sticker.url})")
        e = info_embed(ctx, "Información del sticker", lines)
        e.set_thumbnail(url=sticker.url)
        await ctx.send(embed=e)

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context):
        bot = self.bot
        users = sum(g.member_count or 0 for g in bot.guilds)
        channels = sum(len(g.channels) for g in bot.guilds)
        lines = [
            f"**Servidores:** `{len(bot.guilds):,}`",
            f"**Usuarios:** `{users:,}`",
            f"**Canales:** `{channels:,}`",
            f"**Comandos:** `{len(bot.commands):,}`",
            f"**Latencia:** `{round(bot.latency * 1000)} ms`",
            f"**Activo desde hace:** `{duration_es(time.time() - _STARTED)}`",
            f"**Python:** `{platform.python_version()}` · **discord.py:** `{discord.__version__}`",
        ]
        e = info_embed(ctx, f"Estadísticas de {ctx.guild.me.display_name if ctx.guild else bot.user.name}", lines)
        e.set_thumbnail(url=bot.user.display_avatar.url)
        await ctx.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoExtra(bot))
