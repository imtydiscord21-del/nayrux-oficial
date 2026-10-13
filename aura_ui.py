"""
aura_ui.py — Diseño de los embeds informativos de las capturas (variables, templates,
uso de un comando, AFK...). Todo el aspecto está aquí para poder ajustarlo en un solo sitio.

Estructura de un embed informativo:
  autor      -> quien ejecutó el comando (avatar + nombre)
  título     -> en negrita
  descripción-> en bloque de cita ( > texto )
  campos     -> cada sección con su nombre y sus líneas en bloque de cita
  pie        -> opcional
"""

import time

import discord

import emojis

COLOR = 0x2B2D31


def quote(lines) -> str:
    """Convierte una lista de líneas en un bloque de cita de Discord."""
    if isinstance(lines, str):
        lines = lines.split("\n")
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def code(text: str) -> str:
    return f"`{text}`"


def info_embed(ctx, title: str | None = None, description=None, sections=(), footer: str | None = None) -> discord.Embed:
    """
    sections: [(nombre, [líneas])]. Cada línea ya debe traer su formato (p. ej. con `código`).
    """
    e = discord.Embed(color=COLOR)
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    if title:
        e.title = title
    if description:
        e.description = quote(description)
    for name, lines in sections:
        e.add_field(name=name, value=quote(lines), inline=False)
    if footer:
        e.set_footer(text=footer)
    return e


def variable_lines(items) -> list:
    """[('{user}', 'Mención')] -> ['`{user}` - Mención']"""
    return [f"`{tag}` - {desc}" if desc else f"`{tag}`" for tag, desc in items]


def approve_embed(ctx, text: str) -> discord.Embed:
    """Confirmación con el diseño de la captura de AFK: autor + cita con el check."""
    e = discord.Embed(description=quote(f"{emojis.CHECK} {text}"), color=COLOR)
    e.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
    return e


def ago_es(since_ts: float, now: float | None = None) -> str:
    """'hace 7 segundos', 'hace 1 minuto', 'hace 3 horas', 'hace 2 días'."""
    secs = max(0, int((now if now is not None else time.time()) - since_ts))
    for unit, singular, plural in ((86400, "día", "días"), (3600, "hora", "horas"), (60, "minuto", "minutos")):
        if secs >= unit:
            n = secs // unit
            return f"hace {n} {singular if n == 1 else plural}"
    return f"hace {secs} {'segundo' if secs == 1 else 'segundos'}"


def duration_es(seconds: float) -> str:
    """'7 segundos', '1 minuto', '3 horas' (sin 'hace')."""
    return ago_es(0, now=seconds)[len("hace "):]
