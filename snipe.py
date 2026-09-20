"""
snipe.py — Guarda en memoria el último mensaje borrado y el último editado de
cada canal, y los muestra con ,snipe (,s) y ,editsnipe (,es).

El cache es solo en memoria (se pierde si el bot se reinicia) y guarda
únicamente el último mensaje por canal, no un historial completo.
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone

# channel_id -> dict con datos del último mensaje borrado/editado
_last_deleted: dict[int, dict] = {}
_last_edited: dict[int, dict] = {}


class Snipe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        _last_deleted[message.channel.id] = {
            "content": message.content,
            "author_name": str(message.author),
            "author_avatar": message.author.display_avatar.url,
            "attachments": [a.url for a in message.attachments],
            "deleted_at": datetime.now(timezone.utc),
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.content == after.content:
            return  # ignora ediciones que no cambian el texto (embeds, etc.)
        _last_edited[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author_name": str(before.author),
            "author_avatar": before.author.display_avatar.url,
            "jump_url": after.jump_url,
            "edited_at": datetime.now(timezone.utc),
        }

    @commands.command(name="snipe", aliases=["s"])
    async def snipe(self, ctx: commands.Context):
        """Muestra el último mensaje borrado en este canal."""
        data = _last_deleted.get(ctx.channel.id)
        if not data:
            return await ctx.send(embed=discord.Embed(
                description="No hay ningún mensaje borrado reciente en este canal.",
                color=0x2b2d31,
            ))
        e = discord.Embed(
            description=data["content"] or "*(sin texto — puede haber sido solo un adjunto)*",
            color=0x2b2d31,
        )
        e.set_author(name=data["author_name"], icon_url=data["author_avatar"])
        if data["attachments"]:
            e.set_image(url=data["attachments"][0])
            if len(data["attachments"]) > 1:
                e.add_field(name="Adjuntos", value=f"+{len(data['attachments']) - 1} más", inline=False)
        e.set_footer(text=f"Borrado {discord.utils.format_dt(data['deleted_at'], 'R')}")
        await ctx.send(embed=e)

    @commands.command(name="editsnipe", aliases=["es"])
    async def editsnipe(self, ctx: commands.Context):
        """Muestra el último mensaje editado en este canal."""
        data = _last_edited.get(ctx.channel.id)
        if not data:
            return await ctx.send(embed=discord.Embed(
                description="No hay ningún mensaje editado reciente en este canal.",
                color=0x2b2d31,
            ))
        e = discord.Embed(color=0x2b2d31)
        e.set_author(name=data["author_name"], icon_url=data["author_avatar"])
        e.add_field(name="Antes", value=data["before"][:1024] or "*(vacío)*", inline=False)
        e.add_field(name="Después", value=data["after"][:1024] or "*(vacío)*", inline=False)
        e.description = f"[Ir al mensaje]({data['jump_url']})"
        e.set_footer(text=f"Editado {discord.utils.format_dt(data['edited_at'], 'R')}")
        await ctx.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Snipe(bot))
