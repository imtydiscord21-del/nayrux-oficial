"""
webhook_utils.py — Envía todos los mensajes del bot a través de un webhook
(con el nombre y avatar del bot EN ESE SERVIDOR) en vez de usar el bot directamente.

Nombre y avatar por servidor ("persona"):
    con ellos, sin tocar el perfil global del bot ni otros servidores.
  - Si el dueño usó ,changename / ,changeavatar (premium.py), el nombre y la imagen
    se guardan en la base de datos para ese servidor y los mensajes del bot salen
  - El nombre se manda en cada mensaje (username). El avatar se sube una vez al
    webhook de cada canal (se vuelve a subir solo si cambió).
  - Sin persona configurada se usa el nombre/avatar que el bot tiene en el servidor
    (apodo y avatar por servidor si existen, o los globales).

Los DMs no soportan webhooks (limitación de la API de Discord), así que ahí
siempre se cae de vuelta al envío normal.
"""

import asyncio
import discord
import logging

from config import db

log = logging.getLogger("antinuke.webhook")

WEBHOOK_NAME = "AntiNuke Webhook"

# Cache en memoria: channel_id -> discord.Webhook
_webhook_cache: dict[int, discord.Webhook] = {}

# channel_id -> versión del avatar de persona ya subida al webhook de ese canal
_webhook_avatar_version: dict[int, int] = {}

# Tipos de canal que soportan webhooks
_WEBHOOK_CAPABLE = (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)


def _base_channel(channel):
    """Para hilos, el webhook vive en el canal padre."""
    if isinstance(channel, discord.Thread):
        return channel.parent
    return channel


def forget_guild_webhooks(guild: discord.Guild):
    """Olvida los webhooks cacheados de un servidor (se usa al cambiar la persona)."""
    for channel in guild.channels:
        _webhook_cache.pop(channel.id, None)
        _webhook_avatar_version.pop(channel.id, None)


async def get_channel_webhook(channel) -> discord.Webhook | None:
    """Obtiene (o crea) el webhook del bot para este canal, cacheado."""
    base = _base_channel(channel)
    if base is None or not isinstance(base, _WEBHOOK_CAPABLE):
        return None

    if base.id in _webhook_cache:
        return _webhook_cache[base.id]

    try:
        webhooks = await base.webhooks()
        webhook = discord.utils.get(webhooks, name=WEBHOOK_NAME)
        if webhook is None or webhook.token is None:
            webhook = await base.create_webhook(name=WEBHOOK_NAME, reason="Webhook para mensajes del bot")
    except (discord.Forbidden, discord.HTTPException):
        return None

    _webhook_cache[base.id] = webhook
    return webhook


async def _get_persona(guild_id: int) -> dict:
    """Persona del bot en este servidor. La primera vez se lee de Mongo en un hilo
    para no bloquear el bot; después sale de la caché en memoria."""
    persona = db.peek_persona(guild_id)
    if persona is None:
        try:
            persona = await asyncio.to_thread(db.get_persona, guild_id)
        except Exception as e:
            log.warning(f"No se pudo leer la persona del servidor {guild_id}: {e}")
            persona = {"name": None, "avatar": None, "v": 0}
    return persona


async def _sync_webhook_avatar(webhook: discord.Webhook, base, persona: dict) -> bool:
    """Se asegura de que el webhook del canal tenga el avatar de la persona.
    Devuelve True si el webhook ya tiene (o acaba de recibir) ese avatar."""
    version = persona.get("v", 0)
    if not persona.get("avatar") or not version:
        return False
    if _webhook_avatar_version.get(base.id) == version:
        return True
    try:
        await webhook.edit(avatar=persona["avatar"], reason="Avatar del bot en este servidor")
    except discord.HTTPException as e:
        log.warning(f"No se pudo subir el avatar de persona al webhook de #{getattr(base, 'name', base.id)}: {e}")
        return False
    _webhook_avatar_version[base.id] = version
    return True


async def send_via_webhook(channel, **kwargs):
    """
    Envía un mensaje a través del webhook del bot en ese canal, usando el
    nombre y avatar del bot en ese servidor. Si no se puede (DM, permisos, error
    del webhook, etc.) cae de vuelta a channel.send normal. Devuelve el mensaje enviado.
    """
    if channel.guild is None:
        # DMs no soportan webhooks
        return await channel.send(**kwargs)

    webhook = await get_channel_webhook(channel)
    if webhook is None:
        return await channel.send(**kwargs)

    base = _base_channel(channel)
    me = channel.guild.me
    persona = await _get_persona(channel.guild.id)

    kwargs.setdefault("username", persona.get("name") or me.display_name)
    if "avatar_url" not in kwargs:
        # Con avatar de persona el webhook ya lo tiene guardado; si no se pudo subir
        # (o no hay persona) se manda la URL del avatar actual del bot en el servidor.
        if not await _sync_webhook_avatar(webhook, base, persona):
            kwargs["avatar_url"] = me.display_avatar.url
    kwargs.setdefault("wait", True)

    plain = {k: v for k, v in kwargs.items() if k not in ("username", "avatar_url", "wait")}

    try:
        if isinstance(channel, discord.Thread):
            return await webhook.send(**kwargs, thread=channel)
        return await webhook.send(**kwargs)
    except (discord.NotFound, discord.Forbidden):
        # Webhook borrado o sin permisos: se olvida el cache y se manda normal.
        _webhook_cache.pop(base.id, None)
        _webhook_avatar_version.pop(base.id, None)
        return await channel.send(**plain)
    except (discord.HTTPException, ValueError, TypeError) as e:
        # Cualquier otro fallo del webhook (rate limit, 5xx, nombre rechazado,
        # componentes no permitidos...). No se pierde el mensaje: se manda normal.
        log.warning(f"[{channel.guild.name}] Falló el envío por webhook ({type(e).__name__}: {e}); usando envío normal")
        _webhook_cache.pop(base.id, None)
        _webhook_avatar_version.pop(base.id, None)
        return await channel.send(**plain)


async def edit_via_webhook(channel, message_id: int, **kwargs):
    """Edita un mensaje que fue enviado por el webhook del bot en este canal."""
    webhook = await get_channel_webhook(channel)
    if webhook is None:
        msg = await channel.fetch_message(message_id)
        return await msg.edit(**kwargs)
    try:
        if isinstance(channel, discord.Thread):
            return await webhook.edit_message(message_id, **kwargs, thread=channel)
        return await webhook.edit_message(message_id, **kwargs)
    except discord.NotFound:
        msg = await channel.fetch_message(message_id)
        return await msg.edit(**kwargs)
