"""
emojis.py — Todos los emojis que usa el bot, en un solo lugar.

Cada emoji tiene:
  - una versión NORMAL (unicode) que siempre funciona, y
  - una versión PERSONALIZADA que se toma de un servidor tuyo, buscándola por NOMBRE.

Cómo activar los personalizados (sin copiar IDs):
  1. Crea un servidor y sube ahí tus emojis, con los nombres de la columna "nombre" de abajo.
  2. Mete al bot en ese servidor.
  3. En Railway agrega la variable  EMOJI_GUILD_ID = <ID del servidor>  y reinicia.
Al arrancar, el bot lee ese servidor y usa tus emojis; los que no encuentre quedan con la versión normal.
Con ,emojicheck ves cuáles se encontraron y cuáles no.

Uso en el código:  from emojis import CHECK, ERROR      (o:  import emojis; emojis.CHECK)
"""

import logging
import os

import discord

log = logging.getLogger("antinuke.emojis")

# constante -> (nombres que se buscan en el servidor, versión normal)
EMOJI_TABLE = {
    "ADD":          (("add_blue", "increase"),            "➕"),   # +
    "REMOVE":       (("minus_blue", "decrease"),          "➖"),   # − azul: "se quitó / removed"
    "ERROR":        (("deny", "remove_red"),              "❌"),   # X roja: errores
    "DENY":         (("minus_blue", "decrease"),          "➖"),   # −  "no permitido / desactivado"
    "CHECK":        (("approve", "check_green", "check"), "✅"),   # tilde verde
    "VM_LOCK":      (("lock",),                           "🔒"),
    "VM_UNLOCK":    (("unlock",),                         "🔓"),
    "VM_VER":       (("reveal", "ver"),                   "👁️"),   # mostrar canal
    "VM_NOVER":     (("hide", "nover"),                   "🙈"),   # ocultar canal
    "VM_PANTALLA":  (("rename", "pantalla"),              "🖥️"),
    "VM_NOTAS":     (("info1", "notas"),                  "📝"),
    "VM_MICROFONO": (("claim", "microfono"),              "🎙️"),
    "VM_MENOS":     (("decrease", "menos"),               "➖"),
    "VM_MAS":       (("increase", "mas"),                 "➕"),
    "VM_MARTILLO":  (("kick", "martillo"),                "🔨"),
    "VM_LOGO":      (("voicemaster", "logo"),             "🎧"),
    "EMOJI_SUCCESS": (("approve", "check", "check_green"), "✅"),  # los usa voice.py
    "EMOJI_ERROR":  (("deny", "x_", "remove_red"),        "❌"),
}

# Valores iniciales: las versiones normales
globals().update({const: default for const, (_names, default) in EMOJI_TABLE.items()})

# Imagen de marca del VoiceMaster (se reemplaza por la del emoji "logo" si existe en tu servidor)
LOGO_URL = None

# Qué se encontró en el servidor: {constante: "<:nombre:id>"} (lo llena load_from_guild)
LOADED: dict = {}

# TODOS los emojis del servidor por nombre en minúsculas: {"home": "<:home:123>"}. Sirve para los
# iconos del help y para cualquier otro uso:  emojis.ALL.get("security")
ALL: dict = {}
GUILD_NAME: str | None = None


async def load_from_guild(bot, guild_id=None) -> dict:
    """
    Lee los emojis del servidor EMOJI_GUILD_ID y reemplaza las versiones normales por las
    personalizadas (por nombre). Llamar UNA vez al arrancar, ANTES de cargar los cogs.
    Nunca lanza: si algo falla, se queda con los emojis normales.
    """
    global LOGO_URL, GUILD_NAME
    raw = guild_id or os.getenv("EMOJI_GUILD_ID") or ""
    try:
        guild_id = int(raw)
    except (TypeError, ValueError):
        log.info("EMOJI_GUILD_ID no está configurado: se usan los emojis normales")
        return {}

    try:
        guild = await bot.fetch_guild(guild_id)
        server_emojis = await guild.fetch_emojis()
    except discord.HTTPException as e:
        log.warning(f"No pude leer los emojis del servidor {guild_id} ({e}). ¿El bot está dentro de ese servidor?")
        return {}
    except Exception:
        log.exception("Falló la lectura de emojis; se usan los normales")
        return {}

    GUILD_NAME = getattr(guild, "name", None)
    by_name = {e.name.lower(): e for e in server_emojis if getattr(e, "available", True)}
    found = {}
    for const, (names, _default) in EMOJI_TABLE.items():
        for name in names:
            emoji = by_name.get(name.lower())
            if emoji is not None:
                globals()[const] = str(emoji)
                found[const] = str(emoji)
                if const == "VM_LOGO":
                    LOGO_URL = str(emoji.url)
                break

    LOADED.clear()
    LOADED.update(found)
    ALL.clear()
    ALL.update({name: str(e) for name, e in by_name.items()})
    missing = [c for c in EMOJI_TABLE if c not in found]
    log.info(f"Emojis personalizados: {len(found)} cargados desde '{GUILD_NAME}'"
             + (f"; usando el emoji normal en: {', '.join(missing)}" if missing else ""))
    return found
