"""
premium.py — Comandos "Premium": solo el dueño del bot (OWNER_IDS) o el dueño
del servidor donde se ejecuta el comando pueden usarlos. Cambian el perfil del
bot o del servidor.

Nota: Discord no permite editar la "bio"/descripción de una app vía el token
del bot (solo desde el Developer Portal), así que no existe ,changebio aquí.
"""

import discord
from discord.ext import commands
import aiohttp


def is_bot_or_guild_owner():
    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
            return True
        raise commands.CheckFailure("Este comando es solo para el dueño del bot o el dueño del servidor.")
    return commands.check(predicate)


async def _fetch_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"No pude descargar esa imagen (HTTP {resp.status}).")
            return await resp.read()


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=discord.Embed(description=str(error), color=0xed4245))

    # ── Perfil del bot ───────────────────────────────────────────────────────

    @commands.command(name="changeavatar")
    @is_bot_or_guild_owner()
    async def changeavatar(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await self.bot.user.edit(avatar=data)
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(description=f"Discord rechazó la imagen: {e}", color=0xed4245))
        except ValueError as e:
            return await ctx.send(embed=discord.Embed(description=str(e), color=0xed4245))
        await ctx.send(embed=discord.Embed(description="Avatar del bot actualizado.", color=0x57f287))

    @commands.command(name="changebanner")
    @is_bot_or_guild_owner()
    async def changebanner(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await self.bot.user.edit(banner=data)
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(description=f"Discord rechazó la imagen: {e}", color=0xed4245))
        except ValueError as e:
            return await ctx.send(embed=discord.Embed(description=str(e), color=0xed4245))
        await ctx.send(embed=discord.Embed(description="Banner del bot actualizado.", color=0x57f287))

    @commands.command(name="changename")
    @is_bot_or_guild_owner()
    async def changename(self, ctx: commands.Context, *, name: str):
        if len(name) < 2 or len(name) > 32:
            return await ctx.send(embed=discord.Embed(description="El nombre debe tener entre 2 y 32 caracteres.", color=0xed4245))
        try:
            await self.bot.user.edit(username=name)
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(
                description=f"Discord rechazó el cambio (probablemente el límite de 2 cambios de nombre por hora): {e}",
                color=0xed4245,
            ))
        await ctx.send(embed=discord.Embed(description=f"Nombre del bot cambiado a **{name}**.", color=0x57f287))

    @commands.command(name="resetprofile")
    @is_bot_or_guild_owner()
    async def resetprofile(self, ctx: commands.Context):
        try:
            await self.bot.user.edit(avatar=None, banner=None)
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(description=f"Discord rechazó el cambio: {e}", color=0xed4245))
        await ctx.send(embed=discord.Embed(description="Avatar y banner del bot restablecidos.", color=0x57f287))

    # ── Perfil del servidor ──────────────────────────────────────────────────

    @commands.command(name="guildicon")
    @is_bot_or_guild_owner()
    async def guildicon(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await ctx.guild.edit(icon=data, reason=f"Cambiado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(description=f"Discord rechazó la imagen: {e}", color=0xed4245))
        except ValueError as e:
            return await ctx.send(embed=discord.Embed(description=str(e), color=0xed4245))
        await ctx.send(embed=discord.Embed(description="Ícono del servidor actualizado.", color=0x57f287))

    @commands.command(name="guildbanner")
    @is_bot_or_guild_owner()
    async def guildbanner(self, ctx: commands.Context, url: str):
        try:
            data = await _fetch_bytes(url)
            await ctx.guild.edit(banner=data, reason=f"Cambiado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=discord.Embed(
                description=f"Discord rechazó la imagen (el server necesita nivel de boost para esto): {e}",
                color=0xed4245,
            ))
        except ValueError as e:
            return await ctx.send(embed=discord.Embed(description=str(e), color=0xed4245))
        await ctx.send(embed=discord.Embed(description="Banner del servidor actualizado.", color=0x57f287))

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
        msg = await ctx.send(embed=discord.Embed(description=f"Borré `{len(deleted)}` de tus mensajes.", color=0x57f287))
        await msg.delete(delay=4)


async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
