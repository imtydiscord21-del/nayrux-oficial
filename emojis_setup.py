"""
emoji_setup.py — ,emojicheck (solo dueño del bot): muestra qué emojis personalizados se
encontraron en tu servidor de emojis (EMOJI_GUILD_ID) y cuáles usan la versión normal.
"""

import os

import discord
from discord.ext import commands

import emojis
from aura_ui import COLOR


class EmojiSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="emojicheck", aliases=["emojis"])
    @commands.is_owner()
    async def emojicheck(self, ctx: commands.Context):
        configured = (os.getenv("EMOJI_GUILD_ID") or "").strip()
        lines = []
        for const, (names, _default) in emojis.EMOJI_TABLE.items():
            current = getattr(emojis, const)
            found = const in emojis.LOADED
            lines.append(f"{current} `{'` o `'.join(names)}` — {'del servidor' if found else 'emoji normal'}")

        if not configured:
            head = ("Todavía no configuraste tus emojis, así que se usan los normales.\n"
                    "Agrega en Railway la variable `EMOJI_GUILD_ID` con el ID de tu servidor de emojis y reinicia.")
        elif emojis.GUILD_NAME is None:
            head = (f"No pude leer el servidor `{configured}`. Revisa que el ID sea correcto y que el bot esté dentro de ese servidor.")
        else:
            head = f"Servidor de emojis: **{emojis.GUILD_NAME}** — `{len(emojis.LOADED)}` de `{len(emojis.EMOJI_TABLE)}` encontrados."

        e = discord.Embed(title="Emojis del bot", description=head + "\n\n" + "\n".join(lines), color=COLOR)

        # Iconos del menú de ,help
        import help as help_module
        names = help_module.CATEGORY_EMOJI_NAMES
        have = [k for k, n in names.items() if n in emojis.ALL]
        missing = sorted({n for k, n in names.items() if n not in emojis.ALL})
        text = f"`{len(have)}` de `{len(names)}` categorías tienen icono."
        if missing and emojis.ALL:
            text += "\nFaltan estos nombres en el servidor: " + ", ".join(f"`{n}`" for n in missing)
        e.add_field(name="Iconos del help", value=text, inline=False)
        e.set_footer(text="Para cambiar un emoji, ponle ese nombre en tu servidor de emojis y reinicia el bot.")
        await ctx.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiSetup(bot))
