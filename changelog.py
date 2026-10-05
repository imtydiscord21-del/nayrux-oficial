"""
changelog.py — ,changelog publica una actualización del bot en un canal fijo
(el server/canal de soporte), con el mismo estilo visual del reglamento que
mandaste: título en negrita con emoji, párrafos en cita, links en azul abajo.

El servidor y canal destino están fijos a propósito — esto es para anunciar
cambios del bot en tu server de soporte, no algo configurable por server.
"""

import discord
from discord.ext import commands
from webhook_utils import send_via_webhook

TARGET_GUILD_ID = 1551359725139001426
TARGET_CHANNEL_ID = 1556489770589225021


def _build_changelog_embed(titulo: str, cuerpo: str) -> discord.Embed:
    # Cada párrafo (separado por línea en blanco) se convierte en cita ("> "),
    # igual al estilo de la captura. Los links en [texto](url) que ya estén en
    # el texto se ven azules solos, no hace falta tratarlos aparte.
    paragraphs = [p.strip() for p in cuerpo.split("\n\n") if p.strip()]
    quoted = "\n\n".join(
        "\n".join(f"> {line}" if line else ">" for line in p.split("\n"))
        for p in paragraphs
    )
    return discord.Embed(
        description=f"**{titulo}**\n\n{quoted}",
        color=0x2b2d31,
    )


class Changelog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="changelog")
    @commands.is_owner()
    async def changelog(self, ctx: commands.Context, *, texto: str):
        """
        Publica una actualización del bot en el canal de soporte configurado.
        Formato: ,changelog <título> | <cuerpo>
        El cuerpo puede tener varios párrafos (separados por línea en blanco)
        y links en formato [texto](url), que van a salir en azul.

        Ejemplo:
          ,changelog 🔧 NUEVO: Sistema de Hardban | Agregamos ,hardban, un ban persistente.

          Si alguien lo desbanea, el bot lo vuelve a banear solo.

          [Ver todos los comandos](https://discord.com/channels/...)
        """
        if "|" not in texto:
            return await ctx.send(embed=discord.Embed(
                description="Formato: `,changelog <título> | <cuerpo>`",
                color=0xed4245,
            ))
        titulo, cuerpo = texto.split("|", 1)
        titulo, cuerpo = titulo.strip(), cuerpo.strip()

        guild = self.bot.get_guild(TARGET_GUILD_ID)
        if guild is None:
            return await ctx.send(embed=discord.Embed(description="No encuentro el servidor destino (¿el bot está ahí?).", color=0xed4245))
        channel = guild.get_channel(TARGET_CHANNEL_ID)
        if channel is None:
            return await ctx.send(embed=discord.Embed(description="No encuentro el canal destino.", color=0xed4245))

        embed = _build_changelog_embed(titulo, cuerpo)
        try:
            await send_via_webhook(channel, embed=embed)
        except discord.Forbidden:
            return await ctx.send(embed=discord.Embed(description="No tengo permiso para mandar mensajes en ese canal.", color=0xed4245))

        await ctx.send(embed=discord.Embed(description=f"Publicado en {channel.mention}.", color=0x57f287))


async def setup(bot: commands.Bot):
    await bot.add_cog(Changelog(bot))
