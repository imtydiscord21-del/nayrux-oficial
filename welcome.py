"""
welcome.py — Sistema de bienvenida con sintaxis $v{} (motor compartido en
embed_scripting.py, el mismo que usan ,createembed / ,editembed).

Comandos:
  ,welcome add #canal {embed}$v{message: ...}$v{author: ...}$v{description: ...}
                       $v{thumbnail: {user.avatar}}$v{button: url && texto && emoji && enabled}
  ,welcome list                 — ver entradas activas
  ,welcome remove <n>           — eliminar entrada por número
  ,welcome test                 — previsualizar con tu usuario
  ,welcome off                  — desactivar todos los welcomes de este servidor

Variables disponibles: ver embed_scripting.py (user.*, guild.*, channel.*)
"""

import asyncio
import discord
from discord.ext import commands
from config import db
import logging
from webhook_utils import send_via_webhook
from embed_scripting import parse_code, validate_code, build_message

log = logging.getLogger("antinuke.welcome")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_welcomes(guild_id: int) -> list:
    config = db.get_guild(guild_id)
    return config.get("welcome_entries", [])


def _save_welcomes(guild_id: int, entries: list):
    # Guarda SOLO este campo (atómico). Antes se reescribía el documento completo del
    # servidor, y cualquier otro módulo con una copia vieja de la config podía pisar
    # (borrar) los welcomes sin avisar.
    db.set_guild_field(guild_id, "welcome_entries", entries)


async def _load_welcomes(guild_id: int) -> list | None:
    """Lee los welcomes en un hilo (pymongo es síncrono y bloquearía el bot) y reintenta
    una vez si Mongo falla justo en ese momento. Devuelve None si no se pudo leer."""
    for attempt in (1, 2):
        try:
            return await asyncio.to_thread(_get_welcomes, guild_id)
        except Exception:
            log.exception(f"[{guild_id}] No se pudieron leer los welcomes (intento {attempt}/2)")
            await asyncio.sleep(1.5)
    return None


# ── Cog ──────────────────────────────────────────────────────────────────────

def _get_parsed(entry: dict) -> dict:
    """Compatibilidad: entradas viejas guardaban campos sueltos en vez de 'parsed'."""
    if "parsed" in entry:
        return entry["parsed"]
    return {
        "message": entry.get("message", ""),
        "author": entry.get("author", ""),
        "description": entry.get("description", ""),
        "thumbnail": entry.get("thumbnail", ""),
        "buttons": entry.get("buttons", []),
        "fields": [],
    }


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_channel(self, guild: discord.Guild, channel_id: int):
        """Busca el canal en caché y, si no está, lo pide a Discord (la caché puede
        estar incompleta tras una reconexión)."""
        channel = guild.get_channel(channel_id) or guild.get_thread(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except discord.NotFound:
            log.warning(f"[{guild.name}] El canal de welcome {channel_id} ya no existe — revisa ,welcome list")
        except discord.Forbidden:
            log.warning(f"[{guild.name}] Sin acceso al canal de welcome {channel_id}")
        except discord.HTTPException as e:
            log.warning(f"[{guild.name}] No se pudo obtener el canal de welcome {channel_id}: {e}")
        return None

    async def _send_entry(self, member: discord.Member, index: int, entry: dict):
        guild = member.guild
        channel = await self._resolve_channel(guild, int(entry["channel_id"]))
        if channel is None:
            return

        embed, content, view = build_message(_get_parsed(entry), member=member)
        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if view:
            kwargs["view"] = view
        if not kwargs:
            log.warning(f"[{guild.name}] La entrada #{index} de welcome no tiene contenido para enviar")
            return

        await send_via_webhook(channel, **kwargs)
        log.info(f"[{guild.name}] Welcome #{index} enviado en #{getattr(channel, 'name', channel.id)} para {member}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        entries = await _load_welcomes(member.guild.id)
        if not entries:
            return

        # Cada entrada va por separado: si una falla (canal borrado, embed inválido,
        # permisos...) las demás se envían igual y el error queda en el log.
        for index, entry in enumerate(entries, 1):
            try:
                await self._send_entry(member, index, entry)
            except discord.Forbidden:
                log.warning(f"[{member.guild.name}] Sin permisos para mandar el welcome #{index}")
            except Exception:
                log.exception(f"[{member.guild.name}] Welcome #{index} falló")

    @commands.group(name="welcome", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: commands.Context):
        await ctx.send(embed=discord.Embed(
            description="Usa `,welcome add`, `,welcome list`, `,welcome remove <n>`, `,welcome test`, `,welcome off`.",
            color=0x2b2d31,
        ))

    @welcome.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def welcome_add(self, ctx: commands.Context, channel: discord.TextChannel, *, config_text: str):
        """
        Agrega un mensaje de bienvenida.
        Ejemplo:
          ,welcome add #chat {embed}$v{message: {user.mention}}$v{author: welcome, {user.tag}!}$v{description: hola}$v{thumbnail: {user.avatar}}
        """
        parsed = parse_code(config_text)
        warnings = validate_code(config_text)

        entry = {"channel_id": channel.id, "parsed": parsed}

        entries = _get_welcomes(ctx.guild.id)
        entries.append(entry)
        _save_welcomes(ctx.guild.id, entries)

        embed = discord.Embed(
            description=f"Welcome agregado en {channel.mention}. Entrada #{len(entries)}.\nUsa `,welcome test` para previsualizar.",
            color=0xfee75c if warnings else 0x57f287,
        )
        if warnings:
            embed.add_field(name="Revisa esto", value="\n".join(f"• {w}" for w in warnings), inline=False)
        await ctx.send(embed=embed)

    @welcome.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def welcome_list(self, ctx: commands.Context):
        entries = _get_welcomes(ctx.guild.id)
        if not entries:
            return await ctx.send(embed=discord.Embed(
                description="No hay welcomes configurados.",
                color=0x2b2d31,
            ))

        lines = []
        for i, e in enumerate(entries, 1):
            ch = ctx.guild.get_channel(int(e["channel_id"]))
            ch_mention = ch.mention if ch else f"`{e['channel_id']}` (canal no encontrado — elimina esta entrada y vuelve a agregarla)"
            lines.append(f"**{i}.** {ch_mention}")

        await ctx.send(embed=discord.Embed(
            title="Welcome entries",
            description="\n".join(lines),
            color=0x2b2d31,
        ))

    @welcome.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def welcome_remove(self, ctx: commands.Context, n: int):
        entries = _get_welcomes(ctx.guild.id)
        if n < 1 or n > len(entries):
            return await ctx.send(embed=discord.Embed(
                description=f"Número inválido. Hay `{len(entries)}` entradas.",
                color=0xed4245,
            ))

        removed = entries.pop(n - 1)
        _save_welcomes(ctx.guild.id, entries)

        ch = ctx.guild.get_channel(int(removed["channel_id"]))
        await ctx.send(embed=discord.Embed(
            description=f"Entrada #{n} eliminada ({ch.mention if ch else 'canal desconocido'}).",
            color=0xed4245,
        ))

    @welcome.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx: commands.Context):
        entries = _get_welcomes(ctx.guild.id)
        if not entries:
            return await ctx.send(embed=discord.Embed(
                description="No hay welcomes configurados. Usa `,welcome add` primero.",
                color=0x2b2d31,
            ))

        # Previsualiza la primera entrada en el canal actual
        entry = entries[0]
        embed, content, view = build_message(_get_parsed(entry), member=ctx.author)

        kwargs = {}
        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if view:
            kwargs["view"] = view
        await ctx.send(**kwargs)

    @welcome.command(name="off")
    @commands.has_permissions(manage_guild=True)
    async def welcome_off(self, ctx: commands.Context):
        _save_welcomes(ctx.guild.id, [])
        await ctx.send(embed=discord.Embed(
            description="Todos los welcomes desactivados.",
            color=0xed4245,
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
