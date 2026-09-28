"""
boost.py — Manda un embed cuando alguien boostea el servidor. Misma sintaxis
$v{} que welcome.py (motor compartido en embed_scripting.py).

Comandos:
  ,boost add #canal {embed}$v{message: ...}$v{description: ...}...
  ,boost list
  ,boost remove <n>
  ,boost test
  ,boost off
"""

import discord
from discord.ext import commands
from config import db
import logging
from webhook_utils import send_via_webhook
from embed_scripting import parse_code, validate_code, build_message

log = logging.getLogger("antinuke.boost")


def _get_entries(guild_id: int) -> list:
    config = db.get_guild(guild_id)
    return config.get("boost_entries", [])


def _save_entries(guild_id: int, entries: list):
    config = db.get_guild(guild_id)
    config["boost_entries"] = entries
    db.update_guild(guild_id, config)


class Boost(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Solo dispara cuando alguien EMPIEZA a boostear (None -> con fecha)
        if before.premium_since is not None or after.premium_since is None:
            return

        entries = _get_entries(after.guild.id)
        for entry in entries:
            channel = after.guild.get_channel(int(entry["channel_id"]))
            if not channel:
                continue
            embed, content, view = build_message(entry["parsed"], member=after)
            try:
                kwargs = {}
                if content:
                    kwargs["content"] = content
                if embed:
                    kwargs["embed"] = embed
                if view:
                    kwargs["view"] = view
                await send_via_webhook(channel, **kwargs)
            except discord.Forbidden:
                log.warning(f"[{after.guild.name}] Sin permisos para mandar boost msg en {channel.name}")
            except Exception as e:
                log.error(f"[{after.guild.name}] Boost msg error: {e}")

    @commands.group(name="boost", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def boost(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(
            description="Usa `,boost add`, `,boost list`, `,boost remove <n>`, `,boost test`, `,boost off`.",
            color=0x2b2d31,
        ))

    @boost.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def boost_add(self, ctx: commands.Context, channel: discord.TextChannel, *, config_text: str):
        """
        Agrega un mensaje de boost.
        Ejemplo:
          ,boost add #chat {embed}$v{message: {user.mention} boosteó el server!}$v{color: #f47fff}$v{thumbnail: {user.avatar}}
        """
        parsed = parse_code(config_text)
        warnings = validate_code(config_text)

        entry = {"channel_id": channel.id, "parsed": parsed}
        entries = _get_entries(ctx.guild.id)
        entries.append(entry)
        _save_entries(ctx.guild.id, entries)

        embed = discord.Embed(
            description=f"Mensaje de boost agregado en {channel.mention}. Entrada #{len(entries)}.\nUsa `,boost test` para previsualizar.",
            color=0xfee75c if warnings else 0x57f287,
        )
        if warnings:
            embed.add_field(name="Revisa esto", value="\n".join(f"• {w}" for w in warnings), inline=False)
        await ctx.send(embed=embed)

    @boost.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def boost_list(self, ctx: commands.Context):
        entries = _get_entries(ctx.guild.id)
        if not entries:
            return await ctx.send(embed=discord.Embed(description="No hay mensajes de boost configurados.", color=0x2b2d31))
        lines = []
        for i, e in enumerate(entries, 1):
            ch = ctx.guild.get_channel(int(e["channel_id"]))
            ch_mention = ch.mention if ch else f"`{e['channel_id']}`"
            lines.append(f"**{i}.** {ch_mention}")
        await ctx.send(embed=discord.Embed(title="Boost entries", description="\n".join(lines), color=0x2b2d31))

    @boost.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def boost_remove(self, ctx: commands.Context, n: int):
        entries = _get_entries(ctx.guild.id)
        if n < 1 or n > len(entries):
            return await ctx.send(embed=discord.Embed(description=f"Número inválido. Hay `{len(entries)}` entradas.", color=0xed4245))
        removed = entries.pop(n - 1)
        _save_entries(ctx.guild.id, entries)
        ch = ctx.guild.get_channel(int(removed["channel_id"]))
        await ctx.send(embed=discord.Embed(description=f"Entrada #{n} eliminada ({ch.mention if ch else 'canal desconocido'}).", color=0xed4245))

    @boost.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def boost_test(self, ctx: commands.Context):
        entries = _get_entries(ctx.guild.id)
        if not entries:
            return await ctx.send(embed=discord.Embed(description="No hay mensajes de boost configurados. Usa `,boost add` primero.", color=0x2b2d31))
        embed, content, view = build_message(entries[0]["parsed"], member=ctx.author)
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if view:
            kwargs["view"] = view
        await ctx.send(**kwargs)

    @boost.command(name="off")
    @commands.has_permissions(manage_guild=True)
    async def boost_off(self, ctx: commands.Context):
        _save_entries(ctx.guild.id, [])
        await ctx.send(embed=discord.Embed(description="Mensajes de boost desactivados.", color=0xed4245))


async def setup(bot: commands.Bot):
    await bot.add_cog(Boost(bot))
