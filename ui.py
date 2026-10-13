"""
ui.py — Respuestas estándar del bot (estilo bleed, en español) y listas paginadas.

Todo el aspecto de las respuestas de los módulos nuevos (fake permissions, Instagram...)
sale de aquí, así que para cambiar emojis, colores o el formato de las listas
solo hay que tocar este archivo.

  Éxito:  "<check> @usuario: texto"   (verde)
  Aviso:  "<aviso> @usuario: texto"   (amarillo)
  Error:  "<x> @usuario: texto"       (rojo)
  Lista:  embed con autor, líneas numeradas y pie "Página 1/3 (25 entradas)"
"""

import discord

import emojis

COLOR_SUCCESS = 0x57F287
COLOR_WARN = 0xFEE75C
COLOR_ERROR = 0xED4245
COLOR_NEUTRAL = 0x2B2D31


def _line(ctx, emoji: str, text: str) -> str:
    return f"{emoji} {ctx.author.mention}: {text}"


async def success(ctx, text: str):
    return await ctx.send(embed=discord.Embed(description=_line(ctx, emojis.CHECK, text), color=COLOR_SUCCESS))


async def warn(ctx, text: str):
    return await ctx.send(embed=discord.Embed(description=_line(ctx, emojis.DENY, text), color=COLOR_WARN))


async def error(ctx, text: str):
    return await ctx.send(embed=discord.Embed(description=_line(ctx, emojis.REMOVE, text), color=COLOR_ERROR))


# ── Listas paginadas ─────────────────────────────────────────────────────────

def chunk(entries: list, per_page: int) -> list:
    """Parte una lista en páginas. Siempre devuelve al menos una página."""
    return [entries[i:i + per_page] for i in range(0, len(entries), per_page)] or [[]]


def page_embed(pages: list, index: int, *, title: str, icon_url=None, total: int, noun: str = "entradas") -> discord.Embed:
    e = discord.Embed(description="\n".join(pages[index]), color=COLOR_NEUTRAL)
    e.set_author(name=title, icon_url=icon_url)
    e.set_footer(text=f"Página {index + 1}/{len(pages)} ({total} {noun})")
    return e


class PageView(discord.ui.View):
    """Botones ◀ ▶ para una lista. Solo los puede usar quien ejecutó el comando."""

    def __init__(self, author_id: int, pages: list, *, title: str, icon_url=None, total: int, noun: str = "entradas"):
        super().__init__(timeout=90)
        self.author_id = author_id
        self.pages = pages
        self.index = 0
        self.title = title
        self.icon_url = icon_url
        self.total = total
        self.noun = noun

    def _embed(self) -> discord.Embed:
        return page_embed(self.pages, self.index, title=self.title, icon_url=self.icon_url, total=self.total, noun=self.noun)

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Solo quien ejecutó el comando puede usar estos botones.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.index = (self.index - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.index = (self.index + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self._embed(), view=self)


async def paginate(ctx, entries: list, *, title: str, icon_url=None, per_page: int = 10, noun: str = "entradas"):
    """Manda una lista de líneas. Con una sola página no se ponen botones."""
    pages = chunk(entries, per_page)
    embed = page_embed(pages, 0, title=title, icon_url=icon_url, total=len(entries), noun=noun)
    if len(pages) == 1:
        return await ctx.send(embed=embed)
    view = PageView(ctx.author.id, pages, title=title, icon_url=icon_url, total=len(entries), noun=noun)
    return await ctx.send(embed=embed, view=view)
