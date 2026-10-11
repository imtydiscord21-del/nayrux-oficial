"""
saved_embeds.py — Embeds guardados por nombre, para usarlos con {embed:nombre}
en ,wlc config y ,boostmsg config.

  ,embed create (nombre) (mensaje)   — guarda un embed escrito con la sintaxis {tag: valor}
  ,embed show (nombre)               — lo muestra tal como se vería
  ,embed list                        — lista los embeds guardados
  ,embed delete (nombre)             — lo borra

Ejemplo:
  ,embed create welcome_msg {embed}{title: Bienvenido}{description: hola {user.mention}}{button: label: Reglas && url: https://ejemplo.com}
  ,wlc config #bienvenida {embed:welcome_msg}
"""

import asyncio
import re

import discord
from discord.ext import commands

from config import db
from aura_script import build_message, validate
from aura_ui import info_embed
from ui import success, error, paginate
from webhook_utils import send_via_webhook

NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
MAX_SAVED = 25


def get_saved(guild_id: int, name: str):
    """Texto del embed guardado (o None). Se usa como loader de aura_script.build_message."""
    return db.get_guild(guild_id).get("saved_embeds", {}).get(name.strip().lower())


class SavedEmbeds(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _table(self, guild_id: int) -> dict:
        return dict(db.get_guild(guild_id).get("saved_embeds", {}))

    @commands.group(name="embed", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def embed(self, ctx: commands.Context):
        e = info_embed(
            ctx, "embed",
            ["guarda embeds por nombre para usarlos con `{embed:nombre}`."],
            [("uso", [
                "`,embed create (nombre) (mensaje)`",
                "`,embed show (nombre)`",
                "`,embed list`",
                "`,embed delete (nombre)`",
            ])],
        )
        await ctx.send(embed=e)

    @embed.command(name="create")
    async def embed_create(self, ctx: commands.Context, name: str, *, message: str):
        name = name.lower()
        if not NAME_RE.match(name):
            return await error(ctx, "El nombre solo puede tener letras, números, `-` y `_` (máximo 32).")
        table = self._table(ctx.guild.id)
        if name not in table and len(table) >= MAX_SAVED:
            return await error(ctx, f"Llegaste al límite de `{MAX_SAVED}` embeds guardados.")
        problems = validate(message)
        if problems:
            return await error(ctx, "No pude guardar ese embed:\n" + "\n".join(f"• {p}" for p in problems))
        existed = name in table
        table[name] = message
        db.set_guild_field(ctx.guild.id, "saved_embeds", table)
        verb = "actualizó" if existed else "guardó"
        await success(ctx, f"Se {verb} el embed `{name}`. Úsalo con `{{embed:{name}}}`.")

    @embed.command(name="show")
    async def embed_show(self, ctx: commands.Context, name: str):
        text = get_saved(ctx.guild.id, name)
        if text is None:
            return await error(ctx, f"No existe un embed guardado llamado `{name}`.")
        content, embed, view, errors = build_message(text, ctx.author, ctx.guild)
        kwargs = {k: v for k, v in (("content", content), ("embed", embed), ("view", view)) if v}
        await send_via_webhook(ctx.channel, **kwargs)

    @embed.command(name="list")
    async def embed_list(self, ctx: commands.Context):
        table = self._table(ctx.guild.id)
        if not table:
            return await error(ctx, "No hay embeds guardados en este servidor.")
        lines = [f"`{i}` `{name}`" for i, name in enumerate(sorted(table), start=1)]
        icon = ctx.guild.icon.url if ctx.guild.icon else None
        await paginate(ctx, lines, title="Embeds guardados", icon_url=icon, per_page=10, noun="embeds")

    @embed.command(name="delete", aliases=["remove"])
    async def embed_delete(self, ctx: commands.Context, name: str):
        table = self._table(ctx.guild.id)
        if table.pop(name.lower(), None) is None:
            return await error(ctx, f"No existe un embed guardado llamado `{name}`.")
        db.set_guild_field(ctx.guild.id, "saved_embeds", table)
        await success(ctx, f"Se eliminó el embed `{name.lower()}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SavedEmbeds(bot))
