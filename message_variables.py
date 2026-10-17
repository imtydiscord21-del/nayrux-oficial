"""Common message variables for Zaay's welcome, boost and embed messages."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


USER_VARIABLES = [
    ("{user}", "Nombre y etiqueta del usuario"),
    ("{user.id}", "ID del usuario"),
    ("{user.mention}", "Mención"),
    ("{user.name}", "Nombre de cuenta"),
    ("{user.tag}", "Etiqueta actual de Discord"),
    ("{user.avatar}", "URL del avatar"),
    ("{user.guild_avatar}", "Avatar del usuario en este servidor"),
    ("{user.display_avatar}", "Avatar que se muestra actualmente"),
    ("{user.display_name}", "Nombre para mostrar"),
    ("{user.display}", "Alias compatible: nombre para mostrar"),
    ("{user.joined_at}", "Fecha en que entró al servidor"),
    ("{user.joined_at_timestamp}", "Fecha de ingreso como Unix"),
    ("{user.created_at}", "Fecha en que creó su cuenta"),
    ("{user.created_at_timestamp}", "Creación de cuenta como Unix"),
    ("{user.created}", "Tiempo relativo desde que creó su cuenta"),
    ("{user.boost}", "Sí o No según esté boosteando este servidor"),
    ("{user.boost_since}", "Fecha en que empezó a boostear"),
    ("{user.boost_since_timestamp}", "Inicio del boost como Unix"),
    ("{user.color}", "Color hex del rol más alto"),
    ("{user.top_role}", "Nombre del rol más alto"),
    ("{user.role_list}", "Lista de roles mencionables"),
    ("{user.role_text_list}", "Lista de nombres de roles"),
    ("{user.bot}", "Sí o No según sea una cuenta bot"),
    ("{user.badges_icons}", "Insignias del perfil como emojis"),
    ("{user.badges}", "Insignias del perfil como texto"),
    ("{user.join_position}", "Posición de ingreso al servidor"),
    ("{user.join_position_suffix}", "Posición de ingreso con sufijo"),
]

GUILD_VARIABLES = [
    ("{guild.name}", "Nombre del servidor"),
    ("{guild.id}", "ID del servidor"),
    ("{guild.count}", "Cantidad de miembros"),
    ("{guild.region}", "Región de voz (Discord ya no la proporciona; muestra N/A)"),
    ("{guild.shard}", "Shard de Zaay"),
    ("{guild.owner_id}", "ID del dueño"),
    ("{guild.created_at}", "Fecha de creación del servidor"),
    ("{guild.created_at_timestamp}", "Creación del servidor como Unix"),
    ("{guild.emoji_count}", "Cantidad de emojis"),
    ("{guild.role_count}", "Cantidad de roles"),
    ("{guild.boost_count}", "Boosts activos del servidor"),
    ("{guild.boost_tier}", "Nivel de boost"),
    ("{guild.boost_level}", "Alias de nivel de boost"),
    ("{guild.preferred_locale}", "Idioma preferido del servidor"),
    ("{guild.key_features}", "Funciones activas del servidor"),
    ("{guild.icon}", "URL del ícono"),
    ("{guild.banner}", "URL del banner"),
    ("{guild.splash}", "URL de la imagen de invitación"),
    ("{guild.discovery}", "URL de la imagen de descubrimiento"),
    ("{guild.max_presences}", "Límite de presencias, si Discord lo entrega"),
    ("{guild.max_members}", "Límite de miembros, si Discord lo entrega"),
    ("{guild.max_video_channel_users}", "Límite de usuarios de video"),
    ("{guild.afk_timeout}", "Tiempo de espera AFK en segundos"),
    ("{guild.afk_channel}", "Canal AFK"),
    ("{guild.channels}", "Lista de canales"),
    ("{guild.channels_count}", "Cantidad total de canales"),
    ("{guild.text_channels}", "Lista de canales de texto"),
    ("{guild.text_channels_count}", "Cantidad de canales de texto"),
    ("{guild.voice_channels}", "Lista de canales de voz"),
    ("{guild.voice_channels_count}", "Cantidad de canales de voz"),
    ("{guild.category_channels}", "Lista de categorías"),
    ("{guild.category_channels_count}", "Cantidad de categorías"),
    ("{guild.vanity}", "Código de invitación personalizada"),
]

CHANNEL_VARIABLES = [
    ("{channel.name}", "Nombre del canal de destino"),
    ("{channel.id}", "ID del canal"),
    ("{channel.mention}", "Mención del canal"),
    ("{channel.topic}", "Tema del canal"),
    ("{channel.type}", "Tipo de canal"),
    ("{channel.category_id}", "ID de la categoría"),
    ("{channel.category_name}", "Nombre de la categoría"),
    ("{channel.position}", "Posición del canal"),
    ("{channel.slowmode_delay}", "Lentitud en segundos"),
]

DATETIME_VARIABLES = [
    ("{date.now}", "Fecha actual de Los Ángeles/Pacífico"),
    ("{date.now_proper}", "Fecha actual completa de Los Ángeles/Pacífico"),
    ("{date.now_short}", "Fecha corta de Los Ángeles/Pacífico"),
    ("{date.now_shorter}", "Fecha muy corta de Los Ángeles/Pacífico"),
    ("{time.now}", "Hora de 12 horas de Los Ángeles/Pacífico"),
    ("{time.now_military}", "Hora de 24 horas de Los Ángeles/Pacífico"),
    ("{date.utc_timestamp}", "Hora actual como Unix"),
    ("{date.utc_now}", "Fecha y hora actual en UTC"),
    ("{date.utc_now_proper}", "Fecha completa en UTC"),
    ("{date.utc_now_short}", "Fecha corta en UTC"),
    ("{date.utc_now_shorter}", "Fecha muy corta en UTC"),
    ("{time.utc_now}", "Hora de 12 horas en UTC"),
    ("{time.utc_now_military}", "Hora de 24 horas en UTC"),
    ("{date.mexico_now}", "Fecha y hora de Ciudad de México"),
    ("{time.mexico_now}", "Hora de Ciudad de México"),
]

BOOST_VARIABLES = [
    ("{boost.count}", "Veces que Zaay ha observado que el usuario inició un boost"),
]

_BADGE_ICONS = {
    "staff": "🛠️", "partner": "🤝", "hypesquad": "🏠",
    "bug_hunter": "🐛", "bug_hunter_level_2": "🐛",
    "hypesquad_bravery": "🟠", "hypesquad_brilliance": "🟣",
    "hypesquad_balance": "🟢", "early_supporter": "💜",
    "verified_bot": "✅", "early_verified_bot_developer": "🧰",
    "certified_moderator": "🛡️", "active_developer": "⚡",
}


def _value(value, fallback="N/A"):
    return fallback if value is None or value == "" else str(value)


def _timestamp(value, style="F"):
    if value is None:
        return "N/A"
    return f"<t:{int(value.timestamp())}:{style}>"


def _ordinal(value):
    if value is None:
        return "N/A"
    number = int(value)
    return f"{number}.º"


def variable_values(*, member=None, guild=None, channel=None, boost_count=None):
    """Return Bleed-compatible core placeholders plus Zaay's Mexico-time aliases."""
    guild = guild or getattr(member, "guild", None)
    values = {}

    if member is not None:
        created = getattr(member, "created_at", None)
        joined = getattr(member, "joined_at", None)
        boosted_since = getattr(member, "premium_since", None)
        roles = [r for r in getattr(member, "roles", []) if not getattr(r, "is_default", lambda: False)()]
        flags = getattr(member, "public_flags", None)
        badges = [name for name, enabled in (flags.all() if flags else []) if enabled]
        badge_names = [name.replace("_", " ").title() for name in badges]
        badge_icons = [_BADGE_ICONS[name] for name in badges if name in _BADGE_ICONS]
        guild_avatar = getattr(member, "guild_avatar", None)
        avatar = getattr(member, "display_avatar", None)
        top_role = getattr(member, "top_role", None)
        role_names = [r.name for r in roles]
        role_mentions = [r.mention for r in roles]
        join_position = None
        if guild is not None and joined is not None:
            joined_members = sorted(
                (m for m in getattr(guild, "members", []) if getattr(m, "joined_at", None)),
                key=lambda m: m.joined_at,
            )
            join_position = next((i for i, m in enumerate(joined_members, 1) if m.id == member.id), None)

        values.update({
            "{user}": str(member),
            "{user.id}": member.id,
            "{user.mention}": getattr(member, "mention", str(member)),
            "{user.name}": getattr(member, "name", str(member)),
            "{user.tag}": getattr(member, "discriminator", "0"),
            "{user.avatar}": getattr(avatar, "url", "N/A"),
            "{user.guild_avatar}": getattr(guild_avatar, "url", "N/A"),
            "{user.display_avatar}": getattr(avatar, "url", "N/A"),
            "{user.display_name}": getattr(member, "display_name", str(member)),
            "{user.display}": getattr(member, "display_name", str(member)),
            "{user.joined_at}": _timestamp(joined),
            "{user.joined_at_timestamp}": int(joined.timestamp()) if joined else "N/A",
            "{user.created_at}": _timestamp(created),
            "{user.created_at_timestamp}": int(created.timestamp()) if created else "N/A",
            "{user.created}": _timestamp(created, "R"),
            "{user.boost}": "Sí" if boosted_since else "No",
            "{user.boost_since}": _timestamp(boosted_since),
            "{user.boost_since_timestamp}": int(boosted_since.timestamp()) if boosted_since else "N/A",
            "{user.color}": str(getattr(member, "colour", None)) if getattr(member, "colour", None) else "#000000",
            "{user.top_role}": getattr(top_role, "name", "N/A"),
            "{user.role_list}": ", ".join(role_mentions) or "N/A",
            "{user.role_text_list}": ", ".join(role_names) or "N/A",
            "{user.bot}": "Sí" if getattr(member, "bot", False) else "No",
            "{user.badges_icons}": " ".join(badge_icons) or "N/A",
            "{user.badges}": ", ".join(badge_names) or "N/A",
            "{user.join_position}": join_position or "N/A",
            "{user.join_position_suffix}": _ordinal(join_position),
        })

    if guild is not None:
        created = getattr(guild, "created_at", None)
        afk_channel = getattr(guild, "afk_channel", None)
        icon = getattr(guild, "icon", None)
        banner = getattr(guild, "banner", None)
        splash = getattr(guild, "splash", None)
        discovery = getattr(guild, "discovery_splash", None)
        text_channels = list(getattr(guild, "text_channels", []))
        voice_channels = list(getattr(guild, "voice_channels", []))
        categories = list(getattr(guild, "categories", []))
        channels = list(getattr(guild, "channels", []))
        vanity = getattr(guild, "vanity_url_code", None)
        features = getattr(guild, "features", [])
        values.update({
            "{guild.name}": guild.name,
            "{guild.id}": guild.id,
            "{guild.count}": getattr(guild, "member_count", None) or 0,
            "{guild.region}": "N/A",
            "{guild.shard}": getattr(guild, "shard_id", None),
            "{guild.owner_id}": getattr(guild, "owner_id", None),
            "{guild.created_at}": _timestamp(created),
            "{guild.created_at_timestamp}": int(created.timestamp()) if created else "N/A",
            "{guild.emoji_count}": len(getattr(guild, "emojis", [])),
            "{guild.role_count}": len(getattr(guild, "roles", [])),
            "{guild.boost_count}": getattr(guild, "premium_subscription_count", None) or 0,
            "{guild.boost_tier}": getattr(getattr(guild, "premium_tier", None), "name", getattr(guild, "premium_tier", "N/A")),
            "{guild.boost_level}": getattr(guild, "premium_tier", "N/A"),
            "{guild.preferred_locale}": getattr(guild, "preferred_locale", "N/A"),
            "{guild.key_features}": ", ".join(features) or "N/A",
            "{guild.icon}": getattr(icon, "url", "N/A"),
            "{guild.banner}": getattr(banner, "url", "N/A"),
            "{guild.splash}": getattr(splash, "url", "N/A"),
            "{guild.discovery}": getattr(discovery, "url", "N/A"),
            "{guild.max_presences}": _value(getattr(guild, "max_presences", None)),
            "{guild.max_members}": _value(getattr(guild, "max_members", None)),
            "{guild.max_video_channel_users}": _value(getattr(guild, "max_video_channel_users", None)),
            "{guild.afk_timeout}": getattr(guild, "afk_timeout", 0),
            "{guild.afk_channel}": getattr(afk_channel, "mention", "N/A"),
            "{guild.channels}": ", ".join(c.name for c in channels) or "N/A",
            "{guild.channels_count}": len(channels),
            "{guild.text_channels}": ", ".join(c.name for c in text_channels) or "N/A",
            "{guild.text_channels_count}": len(text_channels),
            "{guild.voice_channels}": ", ".join(c.name for c in voice_channels) or "N/A",
            "{guild.voice_channels_count}": len(voice_channels),
            "{guild.category_channels}": ", ".join(c.name for c in categories) or "N/A",
            "{guild.category_channels_count}": len(categories),
            "{guild.vanity}": vanity or "N/A",
        })

    if channel is not None:
        category = getattr(channel, "category", None)
        values.update({
            "{channel.name}": getattr(channel, "name", "N/A"),
            "{channel.id}": getattr(channel, "id", "N/A"),
            "{channel.mention}": getattr(channel, "mention", "N/A"),
            "{channel.topic}": _value(getattr(channel, "topic", None)),
            "{channel.type}": str(getattr(channel, "type", "N/A")).split(".")[-1],
            "{channel.category_id}": getattr(category, "id", "N/A"),
            "{channel.category_name}": getattr(category, "name", "N/A"),
            "{channel.position}": getattr(channel, "position", "N/A"),
            "{channel.slowmode_delay}": getattr(channel, "slowmode_delay", 0),
        })

    now_pacific = datetime.now(ZoneInfo("America/Los_Angeles"))
    now_utc = datetime.now(timezone.utc)
    now_mexico = datetime.now(ZoneInfo("America/Mexico_City"))
    values.update({
        "{date.now}": now_pacific.strftime("%Y-%m-%d"),
        "{date.now_proper}": now_pacific.strftime("%A, %B %d, %Y"),
        "{date.now_short}": now_pacific.strftime("%m/%d/%y"),
        "{date.now_shorter}": now_pacific.strftime("%m/%d"),
        "{time.now}": now_pacific.strftime("%I:%M %p").lstrip("0"),
        "{time.now_military}": now_pacific.strftime("%H:%M"),
        "{date.utc_timestamp}": int(now_utc.timestamp()),
        "{date.utc_now}": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "{date.utc_now_proper}": now_utc.strftime("%A, %B %d, %Y %H:%M UTC"),
        "{date.utc_now_short}": now_utc.strftime("%m/%d/%y %H:%M UTC"),
        "{date.utc_now_shorter}": now_utc.strftime("%m/%d %H:%M UTC"),
        "{time.utc_now}": now_utc.strftime("%I:%M %p UTC").lstrip("0"),
        "{time.utc_now_military}": now_utc.strftime("%H:%M UTC"),
        "{date.mexico_now}": now_mexico.strftime("%Y-%m-%d %H:%M:%S"),
        "{time.mexico_now}": now_mexico.strftime("%H:%M:%S"),
    })
    if boost_count is not None:
        values["{boost.count}"] = boost_count
    return values
