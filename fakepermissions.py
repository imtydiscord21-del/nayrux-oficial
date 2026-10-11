"""
fakepermissions.py — Permisos falsos (estilo bleed).

Idea: el staff NO tiene el permiso real de Discord (ban_members, kick_members...), así que
un moderador rebelde no puede banear a todo el servidor con un script. En su lugar se le dan
permisos "falsos" por rol: con ellos puede usar los comandos del bot (,ban, ,kick...) pero no
las funciones nativas de Discord.

Comandos (solo el dueño del servidor):
  ,fakepermissions add (rol) (permisos)      — otorga permisos falsos a un rol   (alias: grant)
  ,fakepermissions remove (rol) (permisos)   — quita permisos falsos a un rol    (alias: revoke)
  ,fakepermissions list <rol>                — muestra los permisos falsos
  ,fakepermissions reset                     — borra todos los permisos falsos
  Alias del grupo: ,fakeperms  ,fp

Cómo se aplican:
  install_fake_permissions() (se llama en main.py antes de cargar los cogs) reemplaza
  commands.has_permissions por una versión que, si al usuario le falta el permiso REAL, mira
  si alguno de sus roles tiene ese permiso FALSO (o "administrator" falso, que vale para todo).
  Así funcionan todos los comandos existentes sin tocarlos. ,help <comando> muestra qué
  permisos pide cada uno.

Se guardan en la configuración del servidor: "fake_permissions": {"<id_rol>": ["ban_members", ...]}
"""

import asyncio
import re

import discord
from discord.ext import commands

from config import db
from ui import success, warn, error, paginate

_installed = False


# ── Lógica pura (se prueba sin Discord) ──────────────────────────────────────

def parse_permissions(text: str):
    """'ban_members, kick_members' -> (['ban_members', 'kick_members'], [inválidos])."""
    valid_flags = discord.Permissions.VALID_FLAGS
    valid, invalid = [], []
    for token in re.split(r"[,\s]+", text.strip().lower().replace("`", "")):
        if not token:
            continue
        bucket = valid if token in valid_flags else invalid
        if token not in bucket:
            bucket.append(token)
    return valid, invalid


def fake_permissions_for_roles(config: dict, role_ids) -> set:
    """Une los permisos falsos de todos los roles dados."""
    table = config.get("fake_permissions", {})
    perms = set()
    for rid in role_ids:
        perms.update(table.get(str(rid), []))
    return perms


def still_missing(missing: list, required: dict, fake: set) -> list:
    """De los permisos que le faltan al usuario, cuáles NO cubren sus permisos falsos."""
    if "administrator" in fake:
        return []
    return [p for p in missing if not (required.get(p) is True and p in fake)]


# ── Reemplazo de commands.has_permissions ────────────────────────────────────

def install_fake_permissions():
    """Reemplaza commands.has_permissions (una sola vez) por una que acepta permisos falsos."""
    global _installed
    if _installed:
        return
    _installed = True

    def has_permissions(**perms):
        invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
        if invalid:
            raise TypeError(f"Permisos inválidos: {', '.join(invalid)}")

        async def predicate(ctx: commands.Context) -> bool:
            permissions = ctx.permissions
            missing = [p for p, v in perms.items() if getattr(permissions, p) != v]
            if not missing:
                return True

            if ctx.guild is not None and isinstance(ctx.author, discord.Member):
                config = await asyncio.to_thread(db.get_guild, ctx.guild.id)
                fake = fake_permissions_for_roles(config, (r.id for r in ctx.author.roles))
                if fake:
                    missing = still_missing(missing, perms, fake)
                    if not missing:
                        return True
            raise commands.MissingPermissions(missing)

        # lo lee cmd_help.py para mostrar los permisos en ,help <comando>
        predicate.required_permissions = dict(perms)
        return commands.check(predicate)

    commands.has_permissions = has_permissions


# ── Permiso para administrar: solo el dueño del servidor (o del bot) ─────────

def _owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
            return True
        if await ctx.bot.is_owner(ctx.author):
            return True
        raise commands.CheckFailure("Solo el dueño del servidor puede usar este comando.")
    return commands.check(predicate)


def _fmt(perms) -> str:
    return ", ".join(f"`{p}`" for p in perms)


class FakePermissions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _table(self, guild_id: int) -> dict:
        return dict(db.get_guild(guild_id).get("fake_permissions", {}))

    def _save(self, guild_id: int, table: dict):
        db.set_guild_field(guild_id, "fake_permissions", table)

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.group(name="fakepermissions", aliases=["fakeperms", "fp"], invoke_without_command=True)
    @_owner_only()
    async def fakepermissions(self, ctx: commands.Context):
        from cmd_help import build_command_card
        await ctx.send(embed=build_command_card(ctx))

    @fakepermissions.command(name="add", aliases=["grant"])
    async def fp_add(self, ctx: commands.Context, role: discord.Role, *, permissions: str):
        valid, invalid = parse_permissions(permissions)
        if invalid:
            return await error(ctx, f"Permisos no válidos: {_fmt(invalid)}. Usa nombres como `ban_members` o `kick_members`.")
        if not valid:
            return await error(ctx, "Indica al menos un permiso, por ejemplo `ban_members`.")

        table = self._table(ctx.guild.id)
        current = table.get(str(role.id), [])
        added = [p for p in valid if p not in current]
        if not added:
            return await warn(ctx, f"{role.mention} ya tiene esos permisos falsos.")

        table[str(role.id)] = current + added
        self._save(ctx.guild.id, table)
        await success(ctx, f"Se agregaron los permisos falsos {_fmt(added)} a {role.mention}.")

    @fakepermissions.command(name="remove", aliases=["revoke"])
    async def fp_remove(self, ctx: commands.Context, role: discord.Role, *, permissions: str):
        valid, invalid = parse_permissions(permissions)
        if invalid:
            return await error(ctx, f"Permisos no válidos: {_fmt(invalid)}. Usa nombres como `ban_members` o `kick_members`.")
        if not valid:
            return await error(ctx, "Indica al menos un permiso, por ejemplo `ban_members`.")

        table = self._table(ctx.guild.id)
        current = table.get(str(role.id), [])
        removed = [p for p in valid if p in current]
        if not removed:
            return await error(ctx, f"{role.mention} no tiene esos permisos falsos.")

        left = [p for p in current if p not in removed]
        if left:
            table[str(role.id)] = left
        else:
            table.pop(str(role.id), None)
        self._save(ctx.guild.id, table)
        await success(ctx, f"Se quitaron los permisos falsos {_fmt(removed)} de {role.mention}.")

    @fakepermissions.command(name="list")
    async def fp_list(self, ctx: commands.Context, role: discord.Role = None):
        table = self._table(ctx.guild.id)

        # Se descartan roles que ya no existen
        stale = [rid for rid in table if ctx.guild.get_role(int(rid)) is None]
        if stale:
            for rid in stale:
                table.pop(rid, None)
            self._save(ctx.guild.id, table)

        if role is not None:
            perms = table.get(str(role.id), [])
            if not perms:
                return await error(ctx, f"{role.mention} no tiene permisos falsos.")
            table = {str(role.id): perms}
        if not table:
            return await error(ctx, "No hay permisos falsos configurados.")

        ordered = sorted(table.items(), key=lambda kv: -ctx.guild.get_role(int(kv[0])).position)
        lines = [
            f"`{i}` {ctx.guild.get_role(int(rid)).mention} — {_fmt(perms)}"
            for i, (rid, perms) in enumerate(ordered, start=1)
        ]
        icon = ctx.guild.icon.url if ctx.guild.icon else None
        await paginate(ctx, lines, title="Permisos falsos", icon_url=icon, per_page=10, noun="roles")

    @fakepermissions.command(name="reset")
    async def fp_reset(self, ctx: commands.Context):
        table = self._table(ctx.guild.id)
        if not table:
            return await error(ctx, "No hay permisos falsos configurados.")
        self._save(ctx.guild.id, {})
        await success(ctx, f"Se restablecieron los permisos falsos de `{len(table)}` rol(es).")

    # ── Mantenimiento ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Si borran un rol, se limpia su entrada para que no queden permisos huérfanos."""
        try:
            table = await asyncio.to_thread(self._table, role.guild.id)
            if table.pop(str(role.id), None) is not None:
                await asyncio.to_thread(self._save, role.guild.id, table)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(FakePermissions(bot))
