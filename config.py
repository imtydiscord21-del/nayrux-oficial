import os
import time
from pymongo import MongoClient

DEFAULT_PREFIX = ","

# Timeouts explícitos: sin ellos, si Mongo se cae o Railway corta una conexión
# inactiva, una consulta puede quedarse colgada ~30s bloqueando todo el bot
# (y con eso se pierden eventos como los welcomes). maxIdleTimeMS descarta
# conexiones viejas antes de que el servidor las cierre.
_client = MongoClient(
    os.getenv("MONGO_URI"),
    serverSelectionTimeoutMS=8000,
    connectTimeoutMS=8000,
    socketTimeoutMS=20000,
    maxIdleTimeMS=60000,
    retryReads=True,
    retryWrites=True,
)
_db = _client["bot2"]
_guilds = _db["guilds"]
_users = _db["users"]
_persona = _db["persona"]  # nombre/avatar del bot POR servidor (ver premium.py)


def default_guild_config() -> dict:
    return {
        "prefix": DEFAULT_PREFIX,
        "log_channel": None,
        "log_channels": {},
        "modlog_channel": None,
        "whitelist": [],
        "antinuke_admins": [],
        "warns": {},
        "mod_actions": {},
        "jail": {},
        "jail_backups": {},
        "post_channels": {},
        "posters": [],
        "panic_active": False,
        "panic_state": {},
        "antinuke": {
            "enabled": False,
            "punishment": "ban",
            "ban_threshold": 3,
            "kick_threshold": 3,
            "channel_delete_threshold": 3,
            "channel_create_threshold": 3,
            "role_delete_threshold": 3,
            "role_create_threshold": 3,
            "webhook_create_threshold": 3,
            "mention_threshold": 10,
            "emoji_delete_threshold": 5,
            "ban_window": 10,
            "kick_window": 10,
            "channel_delete_window": 10,
            "channel_create_window": 10,
            "role_delete_window": 10,
            "role_create_window": 10,
            "webhook_create_window": 10,
            "mention_window": 8,
            "emoji_delete_window": 10,
            "anti_ban": True,
            "anti_kick": True,
            "anti_channel_delete": True,
            "anti_channel_create": True,
            "anti_role_delete": True,
            "anti_role_create": True,
            "anti_webhook": True,
            "anti_mention": True,
            "anti_emoji_delete": True,
            "anti_bot_add": True,
            "anti_everyone_mention": True,
            "anti_server_update": True,
            "anti_prune": True,
            "anti_role_add": True,
            "anti_role_perm": True,
            "min_account_age_days": 0,
            "min_guild_age_days": 0,
            "anti_raid": True,
            "raid_threshold": 6,
            "raid_window": 10,
            "raid_lockdown_minutes": 10,
            "anti_spam": True,
            "spam_threshold": 6,
            "spam_window": 5,
            "anti_link": False,
            "anti_invite": True,
            "anti_token": True,
        },
        "link_whitelist": [],
        "bot_persona": {"name": None, "avatar_url": None},
        "module_settings": {
            "link": {"punishment": "mute"},
            "invite": {"punishment": "mute"},
        },
        "log_embed": {
            "color": 0x2b2d31,
            "footer_text": "AntiNuke Protection",
            "thumbnail": True,
        }
    }


class Database:
    def get(self, key, default=None):
        doc = _db["meta"].find_one({"_id": key})
        return doc.get("value", default) if doc else default

    def set(self, key, value):
        _db["meta"].replace_one({"_id": key}, {"_id": key, "value": value}, upsert=True)

    def get_guild(self, guild_id: int) -> dict:
        doc = _guilds.find_one({"_id": str(guild_id)})
        if doc:
            doc.pop("_id", None)
            return doc

        config = default_guild_config()
        _guilds.insert_one({"_id": str(guild_id), **config})
        return config

    def update_guild(self, guild_id: int, config: dict):
        config.pop("_id", None)
        _guilds.replace_one(
            {"_id": str(guild_id)},
            {"_id": str(guild_id), **config},
            upsert=True,
        )

    def set_guild_field(self, guild_id: int, key: str, value):
        """Guarda UN solo campo del servidor de forma atómica ($set), sin reemplazar
        el documento entero. Evita que una copia vieja de la config pise este campo."""
        self.get_guild(guild_id)  # asegura que el documento exista con sus valores por defecto
        _guilds.update_one({"_id": str(guild_id)}, {"$set": {key: value}}, upsert=True)

    # ── Persona del bot por servidor ─────────────────────────────────────────
    # {"name": str|None, "avatar": bytes|None, "v": int}  (v cambia cada vez que
    # cambia el avatar; webhook_utils lo usa para saber si debe resubirlo)

    _persona_cache: dict = {}

    def peek_persona(self, guild_id: int):
        """Devuelve la persona desde la caché en memoria, o None si aún no se cargó
        (así se puede cargar en un hilo sin bloquear el bot)."""
        return self._persona_cache.get(guild_id)

    def get_persona(self, guild_id: int) -> dict:
        cached = self._persona_cache.get(guild_id)
        if cached is not None:
            return cached
        doc = _persona.find_one({"_id": str(guild_id)}) or {}
        persona = {"name": doc.get("name"), "avatar": doc.get("avatar"), "v": int(doc.get("v", 0))}
        self._persona_cache[guild_id] = persona
        return persona

    def set_persona(self, guild_id: int, *, name="__keep__", avatar="__keep__"):
        """Cambia nombre y/o avatar del bot en ESTE servidor. None = quitar; '__keep__' = no tocar."""
        persona = dict(self.get_persona(guild_id))
        if name != "__keep__":
            persona["name"] = name
        if avatar != "__keep__":
            persona["avatar"] = avatar
            # siempre mayor que la versión anterior, aunque dos cambios caigan en el mismo milisegundo
            persona["v"] = max(int(time.time() * 1000), persona.get("v", 0) + 1) if avatar else 0
        _persona.replace_one(
            {"_id": str(guild_id)},
            {"_id": str(guild_id), **persona},
            upsert=True,
        )
        self._persona_cache[guild_id] = persona
        return persona

    def clear_persona(self, guild_id: int):
        _persona.delete_one({"_id": str(guild_id)})
        self._persona_cache[guild_id] = {"name": None, "avatar": None, "v": 0}

    def get_user(self, user_id: int) -> dict:
        """Historial global (no por servidor) de nombres/avatares/nitro de un usuario."""
        doc = _users.find_one({"_id": str(user_id)})
        if doc:
            doc.pop("_id", None)
            return doc

        default = {"usernames": [], "avatars": [], "nitro_detected_at": None}
        _users.insert_one({"_id": str(user_id), **default})
        return default

    def update_user(self, user_id: int, data: dict):
        data.pop("_id", None)
        _users.replace_one(
            {"_id": str(user_id)},
            {"_id": str(user_id), **data},
            upsert=True,
        )


db = Database()
