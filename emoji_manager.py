"""
emoji_manager.py — Comandos para administrar los emojis del servidor: verlos,
buscarlos, robarlos de otros servidores, agregarlos desde una URL, borrarlos,
renombrarlos, copiar varios de una, y poner/quitar ícono de rol.
"""

import discord
from discord.ext import commands
import aiohttp


async def _fetch_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise ValueError(f"No pude descargar eso (HTTP {resp.status}).")
            return await resp.read()


def _err(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=0xed4245)


def _ok(msg: str) -> discord.Embed:
    return discord.Embed(description=msg, color=0x57f287)


class EmojiManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Info & Search ────────────────────────────────────────────────────────

    @commands.command(name="emoji")
    async def emoji_info(self, ctx: commands.Context, emoji: discord.PartialEmoji):
        e = discord.Embed(title=emoji.name, color=0x2b2d31)
        e.set_image(url=emoji.url)
        e.add_field(name="ID", value=str(emoji.id), inline=True)
        e.add_field(name="Animado", value="Sí" if emoji.animated else "No", inline=True)
        guild_emoji = discord.utils.get(ctx.guild.emojis, id=emoji.id)
        if guild_emoji:
            e.add_field(name="Creado", value=discord.utils.format_dt(guild_emoji.created_at, "R"), inline=True)
        await ctx.send(embed=e)

    @commands.command(name="emojilist")
    async def emojilist(self, ctx: commands.Context):
        emojis = ctx.guild.emojis
        if not emojis:
            return await ctx.send(embed=_err("Este servidor no tiene emojis personalizados."))
        lines = [f"{e} `:{e.name}:`" for e in emojis]
        chunks = ["\n".join(lines[i:i + 20]) for i in range(0, len(lines), 20)]
        e = discord.Embed(title=f"Emojis de {ctx.guild.name} ({len(emojis)})", description=chunks[0], color=0x2b2d31)
        if len(chunks) > 1:
            e.set_footer(text=f"Mostrando 20 de {len(emojis)} — usa ,emojisearch para filtrar")
        await ctx.send(embed=e)

    @commands.command(name="emojisearch")
    async def emojisearch(self, ctx: commands.Context, *, query: str):
        query = query.lower()
        found = [e for e in ctx.guild.emojis if query in e.name.lower()]
        if not found:
            return await ctx.send(embed=_err(f"No encontré emojis que coincidan con `{query}`."))
        lines = [f"{e} `:{e.name}:`" for e in found[:30]]
        await ctx.send(embed=discord.Embed(
            title=f"Resultados para \"{query}\" ({len(found)})",
            description="\n".join(lines),
            color=0x2b2d31,
        ))

    @commands.command(name="emojistats")
    async def emojistats(self, ctx: commands.Context):
        emojis = ctx.guild.emojis
        animated = sum(1 for e in emojis if e.animated)
        static = len(emojis) - animated
        limit = ctx.guild.emoji_limit
        e = discord.Embed(title=f"Estadísticas de emojis — {ctx.guild.name}", color=0x2b2d31)
        e.add_field(name="Total", value=f"`{len(emojis)}` / `{limit * 2}`", inline=True)
        e.add_field(name="Estáticos", value=f"`{static}` / `{limit}`", inline=True)
        e.add_field(name="Animados", value=f"`{animated}` / `{limit}`", inline=True)
        await ctx.send(embed=e)

    @commands.command(name="bigemoji")
    async def bigemoji(self, ctx: commands.Context, emoji: discord.PartialEmoji):
        e = discord.Embed(title=emoji.name, color=0x2b2d31)
        e.set_image(url=emoji.url)
        await ctx.send(embed=e)

    # ── Management ───────────────────────────────────────────────────────────

    @commands.command(name="steal")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def steal(self, ctx: commands.Context, emoji: discord.PartialEmoji, name: str = None):
        try:
            data = await _fetch_bytes(emoji.url)
            new_emoji = await ctx.guild.create_custom_emoji(name=name or emoji.name, image=data, reason=f"Robado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=_err(f"Discord rechazó el emoji: {e}"))
        except ValueError as e:
            return await ctx.send(embed=_err(str(e)))
        await ctx.send(embed=_ok(f"Agregado {new_emoji} como `:{new_emoji.name}:`"))

    @commands.command(name="emojiadd")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def emojiadd(self, ctx: commands.Context, name: str, url: str):
        try:
            data = await _fetch_bytes(url)
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=data, reason=f"Agregado por {ctx.author}")
        except discord.HTTPException as e:
            return await ctx.send(embed=_err(f"Discord rechazó el emoji: {e}"))
        except ValueError as e:
            return await ctx.send(embed=_err(str(e)))
        await ctx.send(embed=_ok(f"Agregado {new_emoji} como `:{new_emoji.name}:`"))

    @commands.command(name="deleteemoji")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def deleteemoji(self, ctx: commands.Context, emoji: discord.Emoji):
        name = emoji.name
        await emoji.delete(reason=f"Borrado por {ctx.author}")
        await ctx.send(embed=_ok(f"Emoji `:{name}:` borrado."))

    @commands.command(name="renameemoji")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def renameemoji(self, ctx: commands.Context, emoji: discord.Emoji, new_name: str):
        old_name = emoji.name
        await emoji.edit(name=new_name, reason=f"Renombrado por {ctx.author}")
        await ctx.send(embed=_ok(f"`:{old_name}:` renombrado a `:{new_name}:` {emoji}"))

    @commands.command(name="copyemojis")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def copyemojis(self, ctx: commands.Context, emojis: commands.Greedy[discord.PartialEmoji]):
        if not emojis:
            return await ctx.send(embed=_err("Pasame al menos un emoji para copiar."))
        added, failed = [], []
        for emoji in emojis:
            try:
                data = await _fetch_bytes(emoji.url)
                new_emoji = await ctx.guild.create_custom_emoji(name=emoji.name, image=data, reason=f"Copiado por {ctx.author}")
                added.append(str(new_emoji))
            except (discord.HTTPException, ValueError):
                failed.append(emoji.name)
        desc = f"Agregados: {' '.join(added) if added else 'ninguno'}"
        if failed:
            desc += f"\nFallaron: {', '.join(failed)}"
        await ctx.send(embed=discord.Embed(description=desc, color=0x2b2d31))

    # ── Role Icon ────────────────────────────────────────────────────────────

    async def _set_role_icon(self, ctx: commands.Context, role: discord.Role, icon):
        try:
            if isinstance(icon, discord.PartialEmoji):
                data = await _fetch_bytes(icon.url)
                await role.edit(display_icon=data, reason=f"Ícono cambiado por {ctx.author}")
            elif icon.startswith("http"):
                data = await _fetch_bytes(icon)
                await role.edit(display_icon=data, reason=f"Ícono cambiado por {ctx.author}")
            else:
                await role.edit(display_icon=icon, reason=f"Ícono cambiado por {ctx.author}")  # emoji unicode
        except discord.HTTPException as e:
            return await ctx.send(embed=_err(
                f"Discord rechazó el ícono (el server necesita nivel de boost 2+ para íconos de rol): {e}"
            ))
        except ValueError as e:
            return await ctx.send(embed=_err(str(e)))
        await ctx.send(embed=_ok(f"Ícono de {role.mention} actualizado."))

    @commands.group(name="roleicon", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleicon(self, ctx: commands.Context, role: discord.Role, *, icon: str):
        await self._set_role_icon(ctx, role, icon)

    @roleicon.command(name="set")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleicon_set(self, ctx: commands.Context, role: discord.Role, *, icon: str):
        await self._set_role_icon(ctx, role, icon)

    @roleicon.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleicon_remove(self, ctx: commands.Context, role: discord.Role):
        await role.edit(display_icon=None, reason=f"Ícono quitado por {ctx.author}")
        await ctx.send(embed=_ok(f"Ícono de {role.mention} quitado."))

    @roleicon.command(name="info")
    async def roleicon_info(self, ctx: commands.Context, role: discord.Role):
        if not role.display_icon:
            return await ctx.send(embed=_err(f"{role.mention} no tiene ícono."))
        e = discord.Embed(title=f"Ícono de {role.name}", color=role.color if role.color.value else 0x2b2d31)
        if isinstance(role.display_icon, str):
            e.description = f"Emoji: {role.display_icon}"
        else:
            e.set_thumbnail(url=role.display_icon.url)
        await ctx.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiManager(bot))
