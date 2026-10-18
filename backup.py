"""Persistent server snapshots and best-effort structural restoration."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
from collections import Counter
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import db

log = logging.getLogger("antinuke.backup")

_snapshots: dict[int, dict] = {}
_restore_locks: dict[int, asyncio.Lock] = {}
_last_restore: dict[int, dict] = {}
_AUTO_SNAPSHOT_INTERVAL = 600  # 10 minutes; persisted in MongoDB
_RESTORE_REASON = "AntiNuke: restauración desde backup"


def _asset_hash(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data else None


async def _read_asset(asset) -> bytes | None:
    if asset is None:
        return None
    try:
        return await asset.read()
    except Exception:
        return None


def _serialize_overwrites(overwrites: dict) -> list[dict]:
    result = []
    for target, overwrite in overwrites.items():
        allow, deny = overwrite.pair()
        result.append({
            "id": target.id,
            "type": "role" if isinstance(target, discord.Role) else "member",
            "allow": allow.value,
            "deny": deny.value,
        })
    return sorted(result, key=lambda item: (item["type"], item["id"]))


def _enum_value(value, default=None):
    return getattr(value, "value", default)


def _serialize_channel(channel: discord.abc.GuildChannel) -> dict:
    entry = {
        "id": channel.id,
        "name": channel.name,
        "type": str(channel.type),
        "position": channel.position,
        "category_id": channel.category_id,
        "overwrites": _serialize_overwrites(channel.overwrites),
    }
    if isinstance(channel, discord.TextChannel):
        entry.update(
            topic=channel.topic,
            slowmode_delay=channel.slowmode_delay,
            nsfw=channel.nsfw,
            default_auto_archive_duration=getattr(channel, "default_auto_archive_duration", 1440),
            default_thread_slowmode_delay=getattr(channel, "default_thread_slowmode_delay", 0),
        )
    if isinstance(channel, discord.VoiceChannel):
        entry.update(
            bitrate=channel.bitrate,
            user_limit=channel.user_limit,
            rtc_region=channel.rtc_region,
            video_quality_mode=_enum_value(channel.video_quality_mode),
            nsfw=channel.nsfw,
        )
    if isinstance(channel, discord.StageChannel):
        entry["topic"] = getattr(channel, "topic", None)
    forum_type = getattr(discord, "ForumChannel", ())
    if forum_type and isinstance(channel, forum_type):
        entry.update(
            topic=channel.topic,
            slowmode_delay=channel.slowmode_delay,
            nsfw=channel.nsfw,
            default_auto_archive_duration=channel.default_auto_archive_duration,
            default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
            default_sort_order=_enum_value(channel.default_sort_order),
            default_layout=_enum_value(channel.default_layout),
            available_tags=[
                {
                    "name": tag.name,
                    "moderated": tag.moderated,
                    "emoji": str(tag.emoji) if tag.emoji else None,
                }
                for tag in channel.available_tags
            ],
            default_reaction_emoji=(
                str(channel.default_reaction_emoji)
                if channel.default_reaction_emoji else None
            ),
        )
    return entry


async def _build_snapshot(guild: discord.Guild) -> tuple[dict, list[tuple[dict, str, object]]]:
    roles = []
    for role in sorted(guild.roles, key=lambda item: item.position):
        if role.is_default() or role.managed:
            continue
        roles.append({
            "id": role.id,
            "name": role.name,
            "color": role.color.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "permissions": role.permissions.value,
            "position": role.position,
            "unicode_emoji": getattr(role, "unicode_emoji", None),
            "secondary_color": getattr(getattr(role, "secondary_color", None), "value", None),
            "tertiary_color": getattr(getattr(role, "tertiary_color", None), "value", None),
            "icon": None,
        })

    categories = [
        {
            "id": category.id,
            "name": category.name,
            "position": category.position,
            "overwrites": _serialize_overwrites(category.overwrites),
        }
        for category in guild.categories
    ]
    channels = [
        _serialize_channel(channel)
        for channel in guild.channels
        if not isinstance(channel, discord.CategoryChannel)
        and not isinstance(channel, discord.Thread)
    ]

    guild_data = {
        "name": guild.name,
        "description": guild.description,
        "icon": None,
        "banner": None,
        "splash": None,
        "discovery_splash": None,
        "verification_level": _enum_value(guild.verification_level),
        "explicit_content_filter": _enum_value(guild.explicit_content_filter),
        "default_notifications": _enum_value(guild.default_notifications),
        "preferred_locale": str(guild.preferred_locale),
        "afk_timeout": guild.afk_timeout,
        "afk_channel_id": guild.afk_channel.id if guild.afk_channel else None,
        "system_channel_id": guild.system_channel.id if guild.system_channel else None,
        "system_channel_flags": getattr(guild.system_channel_flags, "value", 0),
        "rules_channel_id": guild.rules_channel.id if guild.rules_channel else None,
        "public_updates_channel_id": guild.public_updates_channel.id if guild.public_updates_channel else None,
        "safety_alerts_channel_id": getattr(guild.safety_alerts_channel, "id", None),
        "premium_progress_bar_enabled": guild.premium_progress_bar_enabled,
        "widget_enabled": getattr(guild, "widget_enabled", None),
        "widget_channel_id": getattr(getattr(guild, "widget_channel", None), "id", None),
    }

    expressions = [emoji for emoji in guild.emojis if getattr(emoji, "available", True)]
    try:
        stickers = await guild.fetch_stickers()
    except Exception:
        stickers = list(getattr(guild, "stickers", []))

    emoji_data = [
        {
            "id": emoji.id,
            "name": emoji.name,
            "roles": [role.id for role in emoji.roles],
            "animated": emoji.animated,
            "available": getattr(emoji, "available", True),
            "asset": None,
        }
        for emoji in expressions
    ]
    sticker_data = [
        {
            "id": sticker.id,
            "name": sticker.name,
            "description": sticker.description or "",
            "tags": getattr(sticker, "tags", "") or "",
            "emoji": getattr(sticker, "emoji", None),
            "format": getattr(sticker.format, "name", "png").lower(),
            "asset": None,
        }
        for sticker in stickers
    ]

    snapshot = {
        "guild_id": guild.id,
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "guild": guild_data,
        "default_role_permissions": guild.default_role.permissions.value,
        "roles": roles,
        "categories": categories,
        "channels": channels,
        "emojis": emoji_data,
        "stickers": sticker_data,
    }

    assets: list[tuple[dict, str, object]] = []
    for key in ("icon", "banner", "splash", "discovery_splash"):
        assets.append((guild_data, key, getattr(guild, key, None)))
    for role, live_role in zip(roles, [r for r in sorted(guild.roles, key=lambda item: item.position) if not r.is_default() and not r.managed]):
        assets.append((role, "icon", live_role.icon))
    for item, live_item in zip(emoji_data, expressions):
        assets.append((item, "asset", live_item.url))
    for item, live_item in zip(sticker_data, stickers):
        assets.append((item, "asset", live_item.url))
    return snapshot, assets


def _snapshot_size(snapshot: dict) -> int:
    return sum(len(snapshot.get(key, [])) for key in ("roles", "categories", "channels", "emojis", "stickers"))


def _is_suspicious_shrink(previous: dict, current: dict) -> bool:
    old_total = _snapshot_size(previous)
    new_total = _snapshot_size(current)
    lost = old_total - new_total
    if lost <= 0:
        return False
    if lost >= max(2, math.ceil(old_total * 0.20)):
        return True
    for key in ("roles", "categories", "channels", "emojis", "stickers"):
        old_count = len(previous.get(key, []))
        group_lost = old_count - len(current.get(key, []))
        if group_lost > 0 and group_lost >= max(1, math.ceil(old_count * 0.40)):
            return True
    return False


async def take_snapshot(guild: discord.Guild, *, force: bool = True) -> dict:
    """Capture the complete supported structure and persist it with its media in MongoDB."""
    lock = _restore_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        return await _take_snapshot_locked(guild, force=force)


async def _take_snapshot_locked(guild: discord.Guild, *, force: bool) -> dict:
    snapshot, assets = await _build_snapshot(guild)
    previous = _snapshots.get(guild.id) or await asyncio.to_thread(db.get_backup, guild.id)
    if previous and not force and _is_suspicious_shrink(previous, snapshot):
        log.warning(
            "[%s] Backup automático omitido: caída sospechosa de objetos (%s → %s). "
            "Se conserva la copia de %s; usa ,backup snapshot para aceptar cambios intencionales.",
            guild.name, _snapshot_size(previous), _snapshot_size(snapshot), previous.get("taken_at"),
        )
        _snapshots[guild.id] = previous
        return previous

    digest_set: set[str] = set()
    asset_failures = []
    semaphore = asyncio.Semaphore(4)

    async def save_asset(target: dict, field: str, asset):
        async with semaphore:
            data = await _read_asset(asset)
            if not data:
                if asset is not None:
                    asset_failures.append(field)
                target[field] = None
                return
            digest = _asset_hash(data)
            target[field] = digest
            digest_set.add(digest)
            await asyncio.to_thread(db.save_backup_asset, guild.id, digest, data)

    await asyncio.gather(*(save_asset(target, field, asset) for target, field, asset in assets))
    if asset_failures and previous:
        log.warning(
            "[%s] Se conserva el backup anterior: no se pudieron leer %d recursos multimedia.",
            guild.name, len(asset_failures),
        )
        _snapshots[guild.id] = previous
        return previous
    await asyncio.to_thread(db.save_backup, guild.id, snapshot)
    await asyncio.to_thread(db.prune_backup_assets, guild.id, digest_set)
    _snapshots[guild.id] = snapshot
    log.info(
        "[%s] Backup guardado: %d roles, %d categorías, %d canales, %d emojis, %d stickers.",
        guild.name, len(snapshot["roles"]), len(snapshot["categories"]),
        len(snapshot["channels"]), len(snapshot["emojis"]), len(snapshot["stickers"]),
    )
    return snapshot


def get_snapshot(guild_id: int) -> dict | None:
    snapshot = _snapshots.get(guild_id)
    if snapshot is None:
        snapshot = db.get_backup(guild_id)
        if snapshot:
            _snapshots[guild_id] = snapshot
    return snapshot


async def _asset_bytes(guild_id: int, digest: str | None) -> bytes | None:
    if not digest:
        return None
    try:
        return await asyncio.to_thread(db.get_backup_asset, guild_id, digest)
    except Exception:
        log.exception("No se pudo leer un archivo del backup %s:%s", guild_id, digest)
        return None


async def _build_overwrites(guild: discord.Guild, raw: list[dict], role_map: dict[int, int]) -> dict:
    overwrites = {}
    for entry in raw:
        old_id = int(entry["id"])
        resolved_id = role_map.get(old_id, old_id)
        target = guild.get_role(resolved_id) if entry["type"] == "role" else guild.get_member(resolved_id)
        if target is None and entry["type"] != "role":
            target = discord.Object(id=resolved_id)
        if target is None:
            continue
        allow = discord.Permissions(int(entry["allow"]))
        deny = discord.Permissions(int(entry["deny"]))
        overwrites[target] = discord.PermissionOverwrite.from_pair(allow, deny)
    return overwrites


def _overwrites_equal(left: dict, right: dict) -> bool:
    return _serialize_overwrites(left) == _serialize_overwrites(right)


async def _asset_matches(guild_id: int, live_asset, digest: str | None) -> bool:
    if not digest:
        return live_asset is None
    data = await _read_asset(live_asset)
    return bool(data) and _asset_hash(data) == digest


async def _restore_guild_settings(guild: discord.Guild, data: dict, channel_map: dict[int, int], report: Counter):
    updates = {}
    simple_fields = (
        "name", "description", "afk_timeout", "premium_progress_bar_enabled", "widget_enabled",
    )
    for key in simple_fields:
        value = data.get(key)
        if key in data and getattr(guild, key, None) != value:
            updates[key] = value

    enum_fields = (
        ("verification_level", discord.VerificationLevel),
        ("explicit_content_filter", discord.ContentFilter),
        ("default_notifications", discord.NotificationLevel),
    )
    for key, enum_type in enum_fields:
        value = data.get(key)
        if value is not None and _enum_value(getattr(guild, key, None)) != value:
            updates[key] = enum_type(value)
    if data.get("preferred_locale") and str(guild.preferred_locale) != data["preferred_locale"]:
        try:
            updates["preferred_locale"] = discord.Locale(data["preferred_locale"])
        except ValueError:
            pass
    if data.get("system_channel_flags") is not None and guild.system_channel_flags.value != data["system_channel_flags"]:
        updates["system_channel_flags"] = discord.SystemChannelFlags._from_value(data["system_channel_flags"])

    for field in ("afk_channel", "system_channel", "rules_channel", "public_updates_channel", "safety_alerts_channel"):
        key = f"{field}_id"
        if key not in data:
            continue
        old_id = data[key]
        mapped_id = channel_map.get(int(old_id), int(old_id)) if old_id else None
        target = guild.get_channel(mapped_id) if mapped_id else None
        if getattr(guild, field, None) != target:
            updates[field] = target
    if data.get("widget_channel_id") is not None:
        old_id = int(data["widget_channel_id"])
        mapped_id = channel_map.get(old_id, old_id)
        if getattr(getattr(guild, "widget_channel", None), "id", None) != mapped_id:
            updates["widget_channel"] = discord.Object(id=mapped_id)

    me = guild.me
    can_manage_guild = bool(me and me.guild_permissions.manage_guild)
    if updates and not can_manage_guild:
        report["skipped"] += len(updates)
        updates.clear()
        log.warning("[%s] Faltó Manage Server para restaurar sus ajustes.", guild.name)
    if updates:
        try:
            await guild.edit(reason=_RESTORE_REASON, **updates)
            report["guild_settings"] += len(updates)
        except (discord.Forbidden, discord.HTTPException) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudieron restaurar ajustes del servidor: %s", guild.name, exc)

    for key in ("icon", "banner", "splash", "discovery_splash"):
        if not can_manage_guild:
            break
        digest = data.get(key)
        live_asset = getattr(guild, key, None)
        if await _asset_matches(guild.id, live_asset, digest):
            continue
        image = await _asset_bytes(guild.id, digest)
        if digest and not image:
            report["skipped"] += 1
            continue
        try:
            await guild.edit(reason=_RESTORE_REASON, **{key: image})
            report["guild_media"] += 1
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudo restaurar %s del servidor: %s", guild.name, key, exc)


async def _restore_roles(guild: discord.Guild, snapshot: dict, report: Counter) -> dict[int, int]:
    role_map: dict[int, int] = {guild.id: guild.id}
    current_roles = {role.id: role for role in guild.roles}
    by_name = {role.name: role for role in guild.roles if not role.is_default() and not role.managed}
    pending_create = []
    pending_update = []

    for data in snapshot.get("roles", []):
        old_id = int(data["id"])
        role = current_roles.get(old_id) or by_name.get(data["name"])
        if role is None:
            pending_create.append(data)
        else:
            role_map[old_id] = role.id
            pending_update.append((role, data))

    me = guild.me
    if not me or not me.guild_permissions.manage_roles:
        report["skipped"] += len(pending_create) + len(pending_update)
        log.warning("[%s] Faltó Manage Roles para restaurar roles.", guild.name)
        return role_map

    semaphore = asyncio.Semaphore(4)

    async def create(data: dict):
        async with semaphore:
            kwargs = {
                "name": data["name"],
                "color": discord.Color(int(data.get("color", 0))),
                "hoist": bool(data.get("hoist")),
                "mentionable": bool(data.get("mentionable")),
                "permissions": discord.Permissions(int(data.get("permissions", 0))),
                "reason": _RESTORE_REASON,
            }
            if "secondary_color" in data:
                kwargs["secondary_color"] = data["secondary_color"]
            if "tertiary_color" in data:
                kwargs["tertiary_color"] = data["tertiary_color"]
            image = await _asset_bytes(guild.id, data.get("icon"))
            if image:
                kwargs["display_icon"] = image
            if data.get("unicode_emoji"):
                kwargs["unicode_emoji"] = data["unicode_emoji"]
            try:
                role = await guild.create_role(**kwargs)
                report["roles_created"] += 1
                return int(data["id"]), role.id
            except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                if "display_icon" in kwargs:
                    kwargs.pop("display_icon", None)
                    try:
                        role = await guild.create_role(**kwargs)
                        report["roles_created"] += 1
                        log.info("[%s] Se restauró el rol %s sin su icono.", guild.name, data["name"])
                        return int(data["id"]), role.id
                    except (discord.Forbidden, discord.HTTPException, TypeError) as retry_exc:
                        exc = retry_exc
                report["failed"] += 1
                log.warning("[%s] No se pudo crear el rol %s: %s", guild.name, data["name"], exc)
                return int(data["id"]), None

    created = await asyncio.gather(*(create(data) for data in pending_create))
    for old_id, new_id in created:
        if new_id:
            role_map[old_id] = new_id

    async def update(role: discord.Role, data: dict):
        async with semaphore:
            changes = {}
            wanted = {
                "name": data["name"],
                "color": discord.Color(int(data.get("color", 0))),
                "hoist": bool(data.get("hoist")),
                "mentionable": bool(data.get("mentionable")),
                "permissions": discord.Permissions(int(data.get("permissions", 0))),
            }
            if "secondary_color" in data and getattr(getattr(role, "secondary_color", None), "value", None) != data["secondary_color"]:
                changes["secondary_color"] = data["secondary_color"]
            if "tertiary_color" in data and getattr(getattr(role, "tertiary_color", None), "value", None) != data["tertiary_color"]:
                changes["tertiary_color"] = data["tertiary_color"]
            for key, value in wanted.items():
                if getattr(role, key) != value:
                    changes[key] = value
            digest = data.get("icon")
            if not await _asset_matches(guild.id, role.icon, digest):
                changes["display_icon"] = await _asset_bytes(guild.id, digest) if digest else None
            unicode_emoji = data.get("unicode_emoji")
            if getattr(role, "unicode_emoji", None) != unicode_emoji:
                changes["unicode_emoji"] = unicode_emoji
            if changes:
                try:
                    await role.edit(reason=_RESTORE_REASON, **changes)
                    report["roles_updated"] += 1
                except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                    report["failed"] += 1
                    log.warning("[%s] No se pudo actualizar el rol %s: %s", guild.name, data["name"], exc)

    await asyncio.gather(*(update(role, data) for role, data in pending_update))

    positions = {}
    for data in snapshot.get("roles", []):
        role_id = role_map.get(int(data["id"]))
        role = guild.get_role(role_id) if role_id else None
        if role and not role.managed and role.position != int(data.get("position", role.position)):
            positions[role] = int(data["position"])
    if positions:
        try:
            await guild.edit_role_positions(positions, reason=_RESTORE_REASON)
        except (discord.Forbidden, discord.HTTPException) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudieron restablecer todas las posiciones de roles: %s", guild.name, exc)

    if guild.default_role.permissions.value != snapshot.get("default_role_permissions", guild.default_role.permissions.value):
        try:
            await guild.default_role.edit(
                permissions=discord.Permissions(snapshot["default_role_permissions"]),
                reason=_RESTORE_REASON,
            )
            report["roles_updated"] += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudieron restaurar permisos de @everyone: %s", guild.name, exc)
    return role_map


async def _restore_categories(guild: discord.Guild, snapshot: dict, role_map: dict[int, int], report: Counter) -> dict[int, int]:
    cat_map: dict[int, int] = {}
    existing_by_id = {item.id: item for item in guild.categories}
    existing_by_name = {item.name: item for item in guild.categories}
    pending_create = []
    pending_update = []
    for data in snapshot.get("categories", []):
        category = existing_by_id.get(int(data["id"])) or existing_by_name.get(data["name"])
        if category is None:
            pending_create.append(data)
        else:
            cat_map[int(data["id"])] = category.id
            pending_update.append((category, data))

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        report["skipped"] += len(pending_create) + len(pending_update)
        log.warning("[%s] Faltó Manage Channels para restaurar categorías.", guild.name)
        return cat_map
    needs_overwrite_permission = any(data.get("overwrites") for data in snapshot.get("categories", []))
    if needs_overwrite_permission and not me.guild_permissions.manage_roles:
        report["skipped"] += len(pending_create) + len(pending_update)
        log.warning("[%s] Faltó Manage Roles para restaurar permisos de categorías.", guild.name)
        return cat_map

    semaphore = asyncio.Semaphore(4)

    async def create(data):
        async with semaphore:
            overwrites = await _build_overwrites(guild, data.get("overwrites", []), role_map)
            try:
                category = await guild.create_category(data["name"], overwrites=overwrites, reason=_RESTORE_REASON)
                report["categories_created"] += 1
                return int(data["id"]), category.id
            except (discord.Forbidden, discord.HTTPException) as exc:
                report["failed"] += 1
                log.warning("[%s] No se pudo crear la categoría %s: %s", guild.name, data["name"], exc)
                return int(data["id"]), None

    created = await asyncio.gather(*(create(data) for data in pending_create))
    for old_id, new_id in created:
        if new_id:
            cat_map[old_id] = new_id

    async def update(category, data):
        async with semaphore:
            kwargs = {}
            if category.name != data["name"]:
                kwargs["name"] = data["name"]
            overwrites = await _build_overwrites(guild, data.get("overwrites", []), role_map)
            if not _overwrites_equal(category.overwrites, overwrites):
                kwargs["overwrites"] = overwrites
            if kwargs:
                try:
                    await category.edit(reason=_RESTORE_REASON, **kwargs)
                    report["categories_updated"] += 1
                except (discord.Forbidden, discord.HTTPException) as exc:
                    report["failed"] += 1
                    log.warning("[%s] No se pudo actualizar la categoría %s: %s", guild.name, data["name"], exc)

    await asyncio.gather(*(update(category, data) for category, data in pending_update))
    return cat_map


def _resolve_default_emoji(raw: str | None, emoji_map: dict[int, int]):
    if not raw:
        return None
    try:
        partial = discord.PartialEmoji.from_str(raw)
        if partial.id:
            return discord.PartialEmoji(
                name=partial.name,
                id=emoji_map.get(partial.id, partial.id),
                animated=partial.animated,
            )
        return raw
    except (ValueError, TypeError):
        return raw


async def _restore_channels(
    guild: discord.Guild,
    snapshot: dict,
    role_map: dict[int, int],
    category_map: dict[int, int],
    emoji_map: dict[int, int],
    report: Counter,
) -> dict[int, int]:
    channel_map: dict[int, int] = dict(category_map)
    categories = {category.id: category for category in guild.categories}
    current = [channel for channel in guild.channels if not isinstance(channel, discord.Thread)]
    current_by_id = {channel.id: channel for channel in current}
    current_by_key = {(str(channel.type), channel.name): channel for channel in current}
    pending_create = []
    pending_update = []
    for data in snapshot.get("channels", []):
        channel = current_by_id.get(int(data["id"])) or current_by_key.get((data["type"], data["name"]))
        if channel is None:
            pending_create.append(data)
        else:
            channel_map[int(data["id"])] = channel.id
            pending_update.append((channel, data))

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        report["skipped"] += len(pending_create) + len(pending_update)
        log.warning("[%s] Faltó Manage Channels para restaurar canales.", guild.name)
        return channel_map
    needs_overwrite_permission = any(data.get("overwrites") for data in snapshot.get("channels", []))
    if needs_overwrite_permission and not me.guild_permissions.manage_roles:
        report["skipped"] += len(pending_create) + len(pending_update)
        log.warning("[%s] Faltó Manage Roles para restaurar permisos de canales.", guild.name)
        return channel_map

    semaphore = asyncio.Semaphore(4)

    async def create(data):
        async with semaphore:
            old_category_id = data.get("category_id")
            new_category_id = channel_map.get(int(old_category_id), int(old_category_id)) if old_category_id else None
            category = categories.get(new_category_id) if new_category_id else None
            overwrites = await _build_overwrites(guild, data.get("overwrites", []), role_map)
            common = {
                "category": category,
                "overwrites": overwrites,
                "reason": _RESTORE_REASON,
            }
            kind = data["type"]
            try:
                if kind in ("text", "news"):
                    channel = await guild.create_text_channel(
                        data["name"], news=kind == "news",
                        topic=data.get("topic") or "", slowmode_delay=data.get("slowmode_delay", 0),
                        nsfw=data.get("nsfw", False),
                        default_auto_archive_duration=data.get("default_auto_archive_duration", 1440),
                        default_thread_slowmode_delay=data.get("default_thread_slowmode_delay", 0),
                        **common,
                    )
                elif kind == "voice":
                    options = {
                        "bitrate": min(data.get("bitrate", 64000), guild.bitrate_limit),
                        "user_limit": data.get("user_limit", 0), "rtc_region": data.get("rtc_region"),
                        "nsfw": data.get("nsfw", False), **common,
                    }
                    if data.get("video_quality_mode") is not None:
                        options["video_quality_mode"] = discord.VideoQualityMode(data["video_quality_mode"])
                    channel = await guild.create_voice_channel(data["name"], **options)
                elif kind == "stage_voice":
                    options = {
                        "bitrate": min(data.get("bitrate", 64000), guild.bitrate_limit),
                        "user_limit": data.get("user_limit", 0), "rtc_region": data.get("rtc_region"),
                        "nsfw": data.get("nsfw", False), **common,
                    }
                    if data.get("video_quality_mode") is not None:
                        options["video_quality_mode"] = discord.VideoQualityMode(data["video_quality_mode"])
                    channel = await guild.create_stage_channel(data["name"], **options)
                elif kind in ("forum", "media"):
                    tags = [
                        discord.ForumTag(
                            name=tag["name"], moderated=tag.get("moderated", False),
                            emoji=_resolve_default_emoji(tag.get("emoji"), emoji_map),
                        )
                        for tag in data.get("available_tags", [])
                    ]
                    forum_kwargs = {
                        "topic": data.get("topic") or "",
                        "slowmode_delay": data.get("slowmode_delay", 0),
                        "nsfw": data.get("nsfw", False),
                        "default_auto_archive_duration": data.get("default_auto_archive_duration", 1440),
                        "default_thread_slowmode_delay": data.get("default_thread_slowmode_delay", 0),
                        "available_tags": tags,
                        **common,
                    }
                    if data.get("default_sort_order") is not None:
                        forum_kwargs["default_sort_order"] = discord.ForumOrderType(data["default_sort_order"])
                    if kind != "media" and data.get("default_layout") is not None:
                        forum_kwargs["default_layout"] = discord.ForumLayoutType(data["default_layout"])
                    default_reaction = _resolve_default_emoji(data.get("default_reaction_emoji"), emoji_map)
                    if default_reaction is not None:
                        forum_kwargs["default_reaction_emoji"] = default_reaction
                    if kind == "media":
                        try:
                            channel = await guild.create_forum(data["name"], media=True, **forum_kwargs)
                        except TypeError:
                            channel = await guild.create_forum(data["name"], **forum_kwargs)
                    else:
                        channel = await guild.create_forum(data["name"], **forum_kwargs)
                else:
                    log.info("[%s] Tipo de canal no restaurable por la librería: %s", guild.name, kind)
                    report["skipped"] += 1
                    return int(data["id"]), None
                report["channels_created"] += 1
                if kind == "stage_voice" and data.get("topic"):
                    try:
                        await channel.edit(topic=data["topic"], reason=_RESTORE_REASON)
                    except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                        report["failed"] += 1
                        log.warning("[%s] No se pudo restaurar el tema del escenario %s: %s", guild.name, data["name"], exc)
                return int(data["id"]), channel.id
            except (discord.Forbidden, discord.HTTPException, TypeError, ValueError) as exc:
                report["failed"] += 1
                log.warning("[%s] No se pudo crear el canal %s (%s): %s", guild.name, data["name"], kind, exc)
                return int(data["id"]), None

    # Create categories first (channel parent ids are mapped against the live guild cache).
    # Categories were restored before this function, so their ids are present in guild.channels.
    created = await asyncio.gather(*(create(data) for data in pending_create))
    for old_id, new_id in created:
        if new_id:
            channel_map[old_id] = new_id

    async def update(channel, data):
        async with semaphore:
            kwargs = {}
            if channel.name != data["name"]:
                kwargs["name"] = data["name"]
            desired_category_id = data.get("category_id")
            mapped_category_id = channel_map.get(int(desired_category_id), int(desired_category_id)) if desired_category_id else None
            desired_category = categories.get(mapped_category_id) if mapped_category_id else None
            if channel.category != desired_category:
                kwargs["category"] = desired_category
            desired_overwrites = await _build_overwrites(guild, data.get("overwrites", []), role_map)
            if not _overwrites_equal(channel.overwrites, desired_overwrites):
                kwargs["overwrites"] = desired_overwrites

            for key in ("topic", "slowmode_delay", "nsfw", "bitrate", "user_limit", "rtc_region"):
                if key in data and getattr(channel, key, None) != data[key]:
                    kwargs[key] = data[key]
            for key in ("default_auto_archive_duration", "default_thread_slowmode_delay"):
                if key in data and getattr(channel, key, None) != data[key]:
                    kwargs[key] = data[key]
            if data.get("video_quality_mode") is not None:
                wanted_mode = discord.VideoQualityMode(data["video_quality_mode"])
                if getattr(channel, "video_quality_mode", None) != wanted_mode:
                    kwargs["video_quality_mode"] = wanted_mode
            if "available_tags" in data and hasattr(channel, "available_tags"):
                current_tags = [
                    {"name": tag.name, "moderated": tag.moderated, "emoji": str(tag.emoji) if tag.emoji else None}
                    for tag in channel.available_tags
                ]
                if current_tags != data["available_tags"]:
                    kwargs["available_tags"] = [
                        discord.ForumTag(
                            name=tag["name"], moderated=tag.get("moderated", False),
                            emoji=_resolve_default_emoji(tag.get("emoji"), emoji_map),
                        )
                        for tag in data["available_tags"]
                    ]
            if data.get("default_sort_order") is not None and getattr(channel, "default_sort_order", None) != discord.ForumOrderType(data["default_sort_order"]):
                kwargs["default_sort_order"] = discord.ForumOrderType(data["default_sort_order"])
            if data.get("default_layout") is not None and getattr(channel, "default_layout", None) != discord.ForumLayoutType(data["default_layout"]):
                kwargs["default_layout"] = discord.ForumLayoutType(data["default_layout"])
            wanted_reaction = _resolve_default_emoji(data.get("default_reaction_emoji"), emoji_map)
            if wanted_reaction is not None and getattr(channel, "default_reaction_emoji", None) != wanted_reaction:
                kwargs["default_reaction_emoji"] = wanted_reaction
            if kwargs:
                try:
                    await channel.edit(reason=_RESTORE_REASON, **kwargs)
                    report["channels_updated"] += 1
                except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                    report["failed"] += 1
                    log.warning("[%s] No se pudo actualizar el canal %s: %s", guild.name, data["name"], exc)

    await asyncio.gather(*(update(channel, data) for channel, data in pending_update))

    # One bulk request restores ordering for every surviving/recreated category and channel.
    channel_positions = []
    for data in snapshot.get("categories", []) + snapshot.get("channels", []):
        mapped_id = channel_map.get(int(data["id"]))
        if mapped_id and guild.get_channel(mapped_id):
            channel_positions.append({"id": mapped_id, "position": int(data.get("position", 0))})
    if channel_positions:
        try:
            await guild._state.http.bulk_channel_update(guild.id, channel_positions, reason=_RESTORE_REASON)
        except (discord.Forbidden, discord.HTTPException, AttributeError) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudieron restaurar todas las posiciones de canales: %s", guild.name, exc)
    return channel_map


async def _restore_expressions(guild: discord.Guild, snapshot: dict, role_map: dict[int, int], report: Counter):
    me = guild.me
    expression_permissions = getattr(me.guild_permissions, "manage_expressions", getattr(me.guild_permissions, "manage_emojis_and_stickers", False)) if me else False
    if not me or not expression_permissions:
        report["skipped"] += len(snapshot.get("emojis", [])) + len(snapshot.get("stickers", []))
        log.warning("[%s] Faltó Manage Expressions para restaurar emojis y stickers.", guild.name)
        return {}
    try:
        current_emojis = await guild.fetch_emojis()
    except (discord.Forbidden, discord.HTTPException):
        current_emojis = list(guild.emojis)
    emoji_by_id = {item.id: item for item in current_emojis}
    emoji_by_name = {item.name: item for item in current_emojis}
    emoji_map = {}
    for data in snapshot.get("emojis", []):
        emoji = emoji_by_id.get(int(data["id"])) or emoji_by_name.get(data["name"])
        if emoji:
            emoji_map[int(data["id"])] = emoji.id
            wanted_roles = [role_map.get(int(role_id), int(role_id)) for role_id in data.get("roles", [])]
            current_roles = sorted(role.id for role in emoji.roles)
            changes = {}
            if emoji.name != data["name"]:
                changes["name"] = data["name"]
            if current_roles != sorted(wanted_roles):
                changes["roles"] = [role for role_id in wanted_roles if (role := guild.get_role(role_id))]
            if changes:
                try:
                    emoji = await emoji.edit(reason=_RESTORE_REASON, **changes)
                    report["emojis_updated"] += 1
                except (discord.Forbidden, discord.HTTPException) as exc:
                    report["failed"] += 1
                    log.warning("[%s] No se pudo restaurar el nombre del emoji %s: %s", guild.name, data["name"], exc)
            continue
        image = await _asset_bytes(guild.id, data.get("asset"))
        if not image:
            report["skipped"] += 1
            continue
        roles = [guild.get_role(role_map.get(int(role_id), int(role_id))) for role_id in data.get("roles", [])]
        roles = [role for role in roles if role]
        try:
            emoji = await guild.create_custom_emoji(
                name=data["name"], image=image, roles=roles, reason=_RESTORE_REASON
            )
            emoji_map[int(data["id"])] = emoji.id
            report["emojis_created"] += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudo restaurar el emoji %s: %s", guild.name, data["name"], exc)

    try:
        current_stickers = await guild.fetch_stickers()
    except (discord.Forbidden, discord.HTTPException):
        current_stickers = list(getattr(guild, "stickers", []))
    sticker_by_id = {item.id: item for item in current_stickers}
    sticker_by_name = {item.name: item for item in current_stickers}
    for data in snapshot.get("stickers", []):
        sticker = sticker_by_id.get(int(data["id"])) or sticker_by_name.get(data["name"])
        if sticker:
            wanted_tags = data.get("tags") or data.get("emoji") or "😀"
            changes = {}
            if sticker.name != data["name"]:
                changes["name"] = data["name"]
            if (sticker.description or "") != data.get("description", ""):
                changes["description"] = data.get("description", "")
            if getattr(sticker, "tags", "") != wanted_tags:
                changes["emoji"] = wanted_tags
            if changes:
                try:
                    await sticker.edit(reason=_RESTORE_REASON, **changes)
                    report["stickers_updated"] += 1
                except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                    report["failed"] += 1
                    log.warning("[%s] No se pudo actualizar el sticker %s: %s", guild.name, data["name"], exc)
            continue
        fmt = data.get("format", "png")
        ext = {"png": "png", "apng": "apng", "gif": "gif"}.get(fmt)
        image = await _asset_bytes(guild.id, data.get("asset"))
        if not image or not ext:
            report["skipped"] += 1
            continue
        try:
            emoji = data.get("tags") or data.get("emoji") or "😀"
            sticker = await guild.create_sticker(
                name=data["name"], description=data.get("description", ""), emoji=emoji,
                file=discord.File(io.BytesIO(image), filename=f"{data['name']}.{ext}"),
                reason=_RESTORE_REASON,
            )
            report["stickers_created"] += 1
        except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
            report["failed"] += 1
            log.warning("[%s] No se pudo restaurar el sticker %s: %s", guild.name, data["name"], exc)
    return emoji_map


def _unmatched_live_items(saved_items: list[dict], live_items: list, key_for_saved, key_for_live) -> list:
    """Match backup objects the same way restoration does, returning live extras."""
    remaining = {item.id: item for item in live_items}
    unmatched_saved = []
    for saved in saved_items:
        item = remaining.pop(int(saved["id"]), None)
        if item is None:
            unmatched_saved.append(saved)
    for saved in unmatched_saved:
        # Match renamed/recreated objects by the same stable display key used by restore.
        key = key_for_saved(saved)
        match = next((item for item in remaining.values() if key_for_live(item) == key), None)
        if match is not None:
            remaining.pop(match.id, None)
    return list(remaining.values())


async def _delete_unbacked_channels(guild: discord.Guild, snapshot: dict, report: Counter):
    """Remove raid-added channels/categories before rebuilding the saved layout."""
    saved_channels = snapshot.get("channels")
    saved_categories = snapshot.get("categories")
    if (
        not isinstance(saved_channels, list)
        or not isinstance(saved_categories, list)
        or not saved_channels
    ):
        report["cleanup_skipped"] += 1
        log.warning(
            "[%s] No se borrarán canales extra: el backup no contiene una estructura verificable.",
            guild.name,
        )
        return

    live_channels = [channel for channel in guild.channels if not isinstance(channel, discord.CategoryChannel)]
    live_categories = list(guild.categories)
    extra_channels = _unmatched_live_items(
        saved_channels,
        live_channels,
        lambda item: (item["type"], item["name"]),
        lambda channel: (str(channel.type), channel.name),
    )
    extra_categories = _unmatched_live_items(
        saved_categories,
        live_categories,
        lambda item: item["name"],
        lambda category: category.name,
    )
    if not extra_channels and not extra_categories:
        return

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        report["skipped"] += len(extra_channels) + len(extra_categories)
        log.warning("[%s] Faltó Manage Channels para borrar canales ajenos al backup.", guild.name)
        return

    semaphore = asyncio.Semaphore(4)

    async def delete(item, counter_key: str):
        async with semaphore:
            try:
                await item.delete(reason="AntiNuke: canal fuera del backup de servidor")
                report[counter_key] += 1
                log.info("[%s] Se eliminó el canal no respaldado: %s (%s).", guild.name, item.name, item.id)
            except (discord.Forbidden, discord.HTTPException) as exc:
                report["failed"] += 1
                log.warning("[%s] No se pudo borrar el canal no respaldado %s: %s", guild.name, item.name, exc)

    # Delete child channels first so categories can be removed cleanly afterwards.
    await asyncio.gather(*(delete(channel, "channels_deleted") for channel in extra_channels))
    await asyncio.gather(*(delete(category, "categories_deleted") for category in extra_categories))


async def restore_guild(guild: discord.Guild, bot: commands.Bot) -> bool:
    """Restore all missing or altered supported settings from the last persistent snapshot."""
    snapshot = get_snapshot(guild.id)
    if not snapshot:
        log.warning("[%s] No hay backup persistente disponible.", guild.name)
        return False
    lock = _restore_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        started = asyncio.get_running_loop().time()
        report = Counter()
        log.info("[%s] Iniciando restauración de backup %s.", guild.name, snapshot.get("taken_at"))
        try:
            await _delete_unbacked_channels(guild, snapshot, report)
            role_map = await _restore_roles(guild, snapshot, report)
            category_map = await _restore_categories(guild, snapshot, role_map, report)
            emoji_map = await _restore_expressions(guild, snapshot, role_map, report)
            channel_map = await _restore_channels(guild, snapshot, role_map, category_map, emoji_map, report)
            await _restore_guild_settings(guild, snapshot.get("guild", {}), channel_map, report)
        except Exception:
            report["failed"] += 1
            log.exception("[%s] Error inesperado durante la restauración.", guild.name)
        elapsed = asyncio.get_running_loop().time() - started
        report["seconds"] = round(elapsed, 2)
        report["objects_restored"] = sum(
            report[key] for key in ("roles_created", "roles_updated", "categories_created", "categories_updated",
                                    "channels_created", "channels_updated", "emojis_created", "emojis_updated",
                                    "stickers_created", "stickers_updated", "channels_deleted", "categories_deleted",
                                    "guild_settings", "guild_media")
        )
        _last_restore[guild.id] = dict(report)
        log.info("[%s] Restauración terminada en %.2fs: %s", guild.name, elapsed, dict(report))
        return True


class Backup(commands.Cog):
    """Mongo-persisted snapshots with periodic refresh and partial restore support."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._snapshot_task: asyncio.Task | None = None

    async def cog_load(self):
        self._snapshot_task = asyncio.create_task(self._periodic_snapshots())

    async def cog_unload(self):
        if self._snapshot_task:
            self._snapshot_task.cancel()

    async def _periodic_snapshots(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                existing = await asyncio.to_thread(db.get_backup, guild.id)
                if existing:
                    _snapshots[guild.id] = existing
                    log.info("[%s] Backup persistente cargado (%s).", guild.name, existing.get("taken_at"))
                else:
                    await take_snapshot(guild, force=True)
            except Exception:
                log.exception("[%s] Falló la carga inicial del backup.", guild.name)
        while not self.bot.is_closed():
            await asyncio.sleep(_AUTO_SNAPSHOT_INTERVAL)
            for guild in self.bot.guilds:
                try:
                    await take_snapshot(guild, force=False)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("[%s] Falló el backup automático.", guild.name)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await take_snapshot(guild, force=True)

    @commands.command(name="backup")
    @commands.is_owner()
    async def backup_cmd(self, ctx: commands.Context, sub: str = "status"):
        """Backup management (bot owner only): snapshot, restore or status."""
        guild = ctx.guild
        if not guild:
            return
        if sub == "snapshot":
            snap = await take_snapshot(guild, force=True)
            return await ctx.send(embed=discord.Embed(
                description=(
                    f"Backup guardado en MongoDB (`{snap['taken_at']}`).\n"
                    f"`{len(snap['roles'])}` roles · `{len(snap['categories'])}` categorías · "
                    f"`{len(snap['channels'])}` canales · `{len(snap['emojis'])}` emojis · "
                    f"`{len(snap['stickers'])}` stickers"
                ), color=0x57f287,
            ))
        if sub == "restore":
            msg = await ctx.send(embed=discord.Embed(
                description="Quitando canales ajenos al backup y reconstruyendo la estructura guardada…",
                color=0xfee75c,
            ))
            ok = await restore_guild(guild, self.bot)
            report = _last_restore.get(guild.id, {})
            if not ok:
                description = "No hay un backup disponible en MongoDB."
                color = 0xed4245
            else:
                description = (
                    f"Restauración terminada en `{report.get('seconds', 0)} s`.\n"
                    f"`{report.get('objects_restored', 0)}` cambios aplicados · "
                    f"`{report.get('failed', 0)}` fallidos · `{report.get('skipped', 0)}` omitidos."
                )
                color = 0x57f287 if not report.get("failed") else 0xfee75c
            await msg.edit(embed=discord.Embed(description=description, color=color))
            return

        snap = get_snapshot(guild.id)
        if not snap:
            return await ctx.send(embed=discord.Embed(description="No hay backup disponible.", color=0x2b2d31))
        report = _last_restore.get(guild.id, {})
        await ctx.send(embed=discord.Embed(
            description=(
                f"**Último backup:** `{snap.get('taken_at', 'desconocido')}`\n"
                f"`{len(snap.get('roles', []))}` roles · `{len(snap.get('categories', []))}` categorías · "
                f"`{len(snap.get('channels', []))}` canales · `{len(snap.get('emojis', []))}` emojis · "
                f"`{len(snap.get('stickers', []))}` stickers\n"
                f"Se actualiza cada 10 minutos. Restauración más reciente: "
                f"`{report.get('seconds', 'sin ejecutar')} s`."
            ), color=0x2b2d31,
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
