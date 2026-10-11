"""
afk.py — Estado AFK (estilo de las capturas).

  ,afk [estado]   — te pone AFK con ese estado (por defecto "AFK")
  ,afklist        — miembros AFK del servidor

Comportamiento:
  - Cuando un AFK escribe un mensaje, deja de estar AFK y el bot le da la bienvenida.
  - Cuando alguien menciona a un AFK, el bot avisa su estado y desde cuándo.
Los datos viven en memoria (rápido, sin consultar Mongo en cada mensaje) y se guardan en la
configuración del servidor ("afk_users") para sobrevivir a reinicios.
"""

import asyncio
import logging
import time

import discord
from discord.ext import commands

from config import db
from aura_ui import COLOR, approve_embed, quote, ago_es, duration_es
from ui import error

log = logging.getLogger("antinuke.afk")

MAX_STATUS = 100
MAX_LIST = 15


class Afk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.table: dict = {}        # guild_id -> {user_id(str): {"status": str, "since": float}}
        self._ignore: set = set()    # ids de mensajes ",afk" para que no se cancelen a sí mismos

    async def cog_load(self):
        try:
            rows = await asyncio.to_thread(db.guilds_with_field, "afk_users")
            self.table = {gid: dict(users) for gid, users in rows}
        except Exception:
            log.exception("No se pudo cargar la lista AFK")

    def _save(self, guild_id: int):
        db.set_guild_field(guild_id, "afk_users", self.table.get(guild_id, {}))

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.command(name="afk")
    @commands.guild_only()
    async def afk(self, ctx: commands.Context, *, status: str = "AFK"):
        status = discord.utils.escape_mentions(status.strip() or "AFK")[:MAX_STATUS]
        self._ignore.add(ctx.message.id)
        self.table.setdefault(ctx.guild.id, {})[str(ctx.author.id)] = {"status": status, "since": time.time()}
        await asyncio.to_thread(self._save, ctx.guild.id)
        await ctx.send(embed=approve_embed(ctx, f"**Ahora** estás AFK con el estado: **{status}**"))

    @commands.command(name="afklist")
    @commands.guild_only()
    async def afklist(self, ctx: commands.Context):
        users = self.table.get(ctx.guild.id, {})
        if not users:
            return await error(ctx, "Nadie está AFK en este servidor.")
        e = discord.Embed(title="Miembros AFK", color=COLOR)
        e.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        ordered = sorted(users.items(), key=lambda kv: kv[1]["since"])
        for uid, data in ordered[:MAX_LIST]:
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"Usuario {uid}"
            e.add_field(name=name, value=quote([data["status"], f"`{ago_es(data['since'])}`"]), inline=False)
        if len(ordered) > MAX_LIST:
            e.set_footer(text=f"y {len(ordered) - MAX_LIST} más")
        await ctx.send(embed=e)

    # ── Eventos ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        users = self.table.get(message.guild.id)
        if not users:
            return  # camino rápido: ningún AFK en este servidor

        # 1) Un AFK vuelve al escribir
        data = users.get(str(message.author.id))
        if data is not None:
            if message.id in self._ignore:
                self._ignore.discard(message.id)
            else:
                ctx = await self.bot.get_context(message)
                if ctx.command is None or ctx.command.name not in ("afk", "afklist"):
                    users.pop(str(message.author.id), None)
                    await asyncio.to_thread(self._save, message.guild.id)
                    e = discord.Embed(
                        description=quote(f"👋 **Bienvenido de vuelta**, estuviste AFK durante **{duration_es(time.time() - data['since'])}**"),
                        color=COLOR,
                    )
                    e.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                    try:
                        await message.reply(embed=e, mention_author=False, delete_after=15)
                    except discord.HTTPException:
                        pass

        # 2) Alguien menciona a un AFK
        lines = []
        for member in message.mentions[:10]:
            info = users.get(str(member.id))
            if info is not None and member.id != message.author.id:
                lines.append(f"**{member.display_name}** está AFK: {info['status']} — `{ago_es(info['since'])}`")
        if lines:
            e = discord.Embed(description=quote(lines[:5]), color=COLOR)
            try:
                await message.reply(embed=e, mention_author=False, delete_after=20)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        users = self.table.get(member.guild.id)
        if users and users.pop(str(member.id), None) is not None:
            await asyncio.to_thread(self._save, member.guild.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Afk(bot))
