"""
snipe.py — Guarda en memoria el último mensaje borrado y el último editado de
cada canal, y los muestra con ,snipe (,s) y ,editsnipe (,es). ,cs (clearsnipe)
borra el dato guardado para que ,s deje de mostrarlo.

El cache es solo en memoria (se pierde si el bot se reinicia) y guarda
únicamente el último mensaje por canal, no un historial completo.
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone

# channel_id -> dict con datos del último mensaje borrado/editado
_last_deleted: dict[int, dict] = {}
_last_edited: dict[int, dict] = {}


def _extract_image(message: discord.Message) -> str | None:
    """Busca una imagen tanto en attachments como en embeds (embed.image/thumbnail),
    porque los mensajes del propio bot son casi todos embeds, no attachments."""
    for a in message.attachments:
        if a.content_type and a.content_type.startswith("image/"):
            return a.url
    for embed in message.embeds:
        if embed.image and embed.image.url:
            return embed.image.url
        if embed.thumbnail and embed.thumbnail.url:
            return embed.thumbnail.url
    return None


def _extract_text(message: discord.Message) -> str:
    if message.content:
        return message.content
    for embed in message.embeds:
        if embed.description:
            return embed.description
        if embed.title:
            return embed.title
    return ""


class Snipe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        _last_deleted[message.channel.id] = {
            "content": _extract_text(message),
            "author_name": message.author.display_name,
            "author_avatar": message.author.display_avatar.url,
            "image": _extract_image(message),
            "extra_count": max(0, len(message.attachments) - 1),
            "deleted_at": datetime.now(timezone.utc),
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.content == after.content:
            return  # ignora ediciones que no cambian el texto (embeds, etc.)
        _last_edited[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author_name": before.author.display_name,
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
        if data["image"]:
            e.set_image(url=data["image"])
        if data["extra_count"]:
            e.add_field(name="Adjuntos", value=f"+{data['extra_count']} más", inline=False)
        e.set_footer(text=f"Borrado {discord.utils.format_dt(data['deleted_at'], 'R')}")
        await ctx.send(embed=e)

    @commands.command(name="cs", aliases=["clearsnipe"])
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: commands.Context):
        """Borra el mensaje sniped guardado de este canal — ,s deja de mostrarlo hasta que se borre algo nuevo."""
        had_deleted = _last_deleted.pop(ctx.channel.id, None) is not None
        had_edited = _last_edited.pop(ctx.channel.id, None) is not None
        if not had_deleted and not had_edited:
            return await ctx.send(embed=discord.Embed(description="No había nada guardado en este canal.", color=0x2b2d31))
        await ctx.send(embed=discord.Embed(description="Snipe de este canal borrado.", color=0x57f287))

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
