"""
github_updates.py — Anuncia en un canal de Discord cada actualización que subas a GitHub.

Cuando haces push al repo, GitHub avisa al bot (webhook) y el bot publica un mensaje con:
  - lo que escribiste en el commit (tu "resumen" y "descripción"),
  - los archivos NUEVOS, MODIFICADOS y ELIMINADOS (con una etiqueta legible si el archivo la tiene),
  - un enlace para ver los cambios en GitHub.

Comandos (solo el dueño del bot):
  ,updates channel (#canal)   — servidor y canal donde se anuncian las actualizaciones
  ,updates status             — configuración actual y si el servidor de avisos está activo
  ,updates test               — manda un anuncio de prueba
  ,updates off                — deja de anunciar

Configuración (variables de Railway):
  GITHUB_WEBHOOK_SECRET   (obligatoria) una clave larga inventada por ti; la misma va en GitHub.
                          Sin ella el servidor de avisos NO se enciende.
  GITHUB_UPDATES_BRANCH   rama a anunciar (por defecto "main")
  UPDATES_CHANNEL_ID      canal por defecto si no usas ,updates channel
  PORT                    lo pone Railway solo

En GitHub:  repo → Settings → Webhooks → Add webhook
  Payload URL   https://TU-DOMINIO-DE-RAILWAY/github
  Content type  application/json
  Secret        la misma de GITHUB_WEBHOOK_SECRET
  Events        "Just the push event"
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlencode
import time

import discord
from aiohttp import ClientError, ClientSession, ClientTimeout, web
from discord.ext import commands

from config import db
from ui import success, error

log = logging.getLogger("antinuke.github_updates")

SECRET = os.getenv("GITHUB_WEBHOOK_SECRET") or ""
BRANCH = os.getenv("GITHUB_UPDATES_BRANCH", "main")
STATE_KEY = "github_updates"
WEBSITE_DIR = Path(__file__).resolve().parent / "website"
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1559390674472931422")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://zayy-bot-production.up.railway.app/api/auth/callback")
DISCORD_API = "https://discord.com/api/v10"

try:
    PORT = int(os.getenv("PORT", "8080"))
except ValueError:
    PORT = 8080

MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_COMMITS_SHOWN = 6
COLOR = 0x2B2D31
COMMAND_DECORATOR_RE = re.compile(
    r"@(?P<decorator>[\w.]*?(?:hybrid_command|hybrid_group|command|group))"
    r"[ \t]*(?:\((?P<args>[^)]*)\))?[ \t]*(?:\n[ \t]*@[^\n]+)*"
    r"(?:\n[ \t]*(?:async[ \t]+)?def[ \t]+(?P<function>[A-Za-z_]\w*))?",
    re.MULTILINE | re.DOTALL,
)

_COMMIT_KIND_RE = re.compile(
    r"^\s*(feat(?:ure)?|fix|bugfix|perf(?:ormance)?|refactor|docs?|chore|security|style|test)(?:\([^)]*\))?!?:\s*",
    re.IGNORECASE,
)
_COMMIT_KIND_LABELS = {
    "feat": "✨ Función nueva", "feature": "✨ Función nueva",
    "fix": "🛠️ Corrección", "bugfix": "🛠️ Corrección",
    "perf": "⚡ Rendimiento", "performance": "⚡ Rendimiento",
    "refactor": "🧹 Mejora interna", "doc": "📚 Documentación", "docs": "📚 Documentación",
    "chore": "🔧 Mantenimiento", "security": "🔒 Seguridad",
    "style": "🎨 Ajuste visual", "test": "🧪 Pruebas",
}

# Etiquetas legibles para que el anuncio se entienda sin saber de archivos.
FILE_LABELS = {
    "main.py": "Núcleo del bot",
    "help.py": "Menú de ayuda (`.help`)",
    "cmd_help.py": "Fichas de ayuda de los comandos",
    "ui.py": "Respuestas estándar del bot",
    "emojis.py": "Emojis del bot",
    "emoji_setup.py": "Revisión de emojis (`.emojicheck`)",
    "config.py": "Base de datos",
    "webhook_utils.py": "Envío de mensajes por webhook",
    "welcome.py": "Bienvenidas (`.welcome`)",
    "wlc.py": "Bienvenida (`.wlc`)",
    "boost.py": "Mensajes de boost (`.boost`)",
    "boostmsg.py": "Mensajes de boost (`.boostmsg`)",
    "afk.py": "AFK (`.afk`)",
    "fakepermissions.py": "Permisos falsos (`.fakepermissions`)",
    "instagram.py": "Instagram (`.instagram`)",
    "saved_embeds.py": "Embeds guardados (`.embed`)",
    "info_extra.py": "Más comandos de información",
    "vanity_sniper.py": "Reclamar vanity (`.vanityclaim`)",
    "voice.py": "VoiceMaster",
    "moderation.py": "Moderación",
    "antinuke.py": "Antinuke",
    "whitelist.py": "Whitelist",
    "backup.py": "Respaldos",
    "snipe.py": "Snipe (`.s`)",
    "premium.py": "Premium",
    "ia_chat.py": "Chat con IA",
    "github_updates.py": "Anuncios de actualizaciones",
}

# Mensajes que GitHub escribe solo al subir archivos desde la web; no aportan nada al anuncio.
AUTO_MESSAGE_RE = re.compile(
    r"^(?:(?:Create|Update|Delete|Rename)\s+[\w./ -]*?[\w-]+\.\w+|Add files via upload)$", re.IGNORECASE
)


# ── Lógica pura (se prueba sin red ni Discord) ───────────────────────────────

def verify_signature(secret: str, body: bytes, header) -> bool:
    """Comprueba la firma X-Hub-Signature-256 que GitHub pone con tu clave secreta."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def _is_auto_message(message: str) -> bool:
    """True para los mensajes que GitHub escribe solo ('Create x.py', 'Update y.py', 'Add files via upload')."""
    first, _, rest = message.strip().partition("\n")
    return not rest.strip() and bool(AUTO_MESSAGE_RE.match(first.strip()))


def summarize_push(payload: dict) -> dict:
    """Resume un evento push: mensajes de commit y archivos nuevos/modificados/eliminados (neto)."""
    status: dict = {}
    notes = []
    commits = payload.get("commits") or []
    for commit in commits:                       # GitHub los manda del más viejo al más nuevo
        for path in commit.get("added") or []:
            status[path] = "modified" if status.get(path) == "removed" else (status.get(path) or "added")
        for path in commit.get("modified") or []:
            if status.get(path) != "added":
                status[path] = "modified"
        for path in commit.get("removed") or []:
            if status.get(path) == "added":
                status.pop(path)                 # se creó y se borró en el mismo push: no cuenta
            else:
                status[path] = "removed"

        message = (commit.get("message") or "").strip()
        if message and not _is_auto_message(message):
            first, _, body = message.partition("\n")
            author = (commit.get("author") or {}).get("name") or ""
            notes.append({"title": first.strip(), "body": body.strip(), "author": author})

    return {
        "repo": (payload.get("repository") or {}).get("full_name", ""),
        "branch": (payload.get("ref") or "").replace("refs/heads/", ""),
        "pusher": (payload.get("pusher") or {}).get("name", ""),
        "compare": payload.get("compare") or "",
        "commit_count": len(commits),
        "notes": notes,
        "commands_added": [],
        "commands_removed": [],
        "commands_updated": [],
        "added": sorted(p for p, s in status.items() if s == "added"),
        "modified": sorted(p for p, s in status.items() if s == "modified"),
        "removed": sorted(p for p, s in status.items() if s == "removed"),
    }


def _commands_from_patch(patch: str, marker: str) -> list[dict]:
    lines = [line[1:] for line in patch.splitlines() if line.startswith(marker) and not line.startswith(marker * 3)]
    code = "\n".join(lines)
    commands = []
    for match in COMMAND_DECORATOR_RE.finditer(code):
        args = match.group("args") or ""
        name = re.search(r"\bname\s*=\s*['\"]([^'\"]+)['\"]", args)
        command = name.group(1) if name else match.group("function")
        if not command:
            continue
        decorator = match.group("decorator")
        commands.append({
            "name": command,
            "kind": "slash" if "app_commands" in decorator else ("hybrid" if "hybrid_" in decorator else "prefix"),
        })
    return commands


def _commands_from_files(files: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    added, removed = {}, {}
    for file in files:
        path = file.get("filename", "")
        label = FILE_LABELS.get(path.rsplit("/", 1)[-1])
        for marker, target in (("+", added), ("-", removed)):
            for command in _commands_from_patch(file.get("patch") or "", marker):
                command["area"] = label
                target[(command["kind"], command["name"])] = command
    updated = {key: added.pop(key) for key in added.keys() & removed.keys()}
    for key in updated:
        removed.pop(key)
    sort = lambda commands: sorted(commands.values(), key=lambda command: command["name"])
    return sort(added), sort(removed), sort(updated)


async def _commands_from_github_compare(payload: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Lee el diff público del push para detectar comandos en los cambios de Python."""
    repo = (payload.get("repository") or {}).get("full_name", "")
    before, after = payload.get("before", ""), payload.get("after", "")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not all(re.fullmatch(r"[0-9a-f]{40,64}", sha) for sha in (before, after)):
        return [], [], []
    if before == "0" * len(before):
        return [], [], []

    url = f"https://api.github.com/repos/{repo}/compare/{before}...{after}"
    try:
        async with ClientSession(timeout=ClientTimeout(total=8)) as session:
            async with session.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ZaayBot"}) as response:
                if response.status != 200:
                    log.warning("GitHub compare respondió %s; anunciaré el resumen del commit sin detectar comandos", response.status)
                    return [], [], []
                comparison = await response.json()
    except (ClientError, asyncio.TimeoutError, ValueError):
        log.warning("No pude leer el diff de GitHub para detectar comandos", exc_info=True)
        return [], [], []

    files = [file for file in comparison.get("files", []) if file.get("filename", "").endswith(".py")]
    return _commands_from_files(files)


def _change_line(note: dict) -> str:
    """Presenta el tipo y la explicación del commit sin inventar detalles."""
    title = note["title"]
    match = _COMMIT_KIND_RE.match(title)
    kind = _COMMIT_KIND_LABELS.get(match.group(1).lower()) if match else None
    if match:
        title = title[match.end():].strip()
    heading = f"**{kind}: {title}**" if kind else f"**{title}**"
    body = note.get("body", "").replace("\n", " ").strip()
    if len(body) > 220:
        body = body[:219].rstrip() + "…"
    return f"• {heading}" + (f"\n  {body}" if body else "")


def _command_line(command: dict) -> str:
    name = command["name"]
    if command["kind"] == "slash":
        shown = f"/{name}"
    elif command["kind"] == "hybrid":
        shown = f"`,{name}` y `/{name}`"
    else:
        shown = f"`,{name}`"
    return f"• {shown}" + (f" — {command['area']}" if command.get("area") else "")


def build_announcement(summary: dict) -> discord.Embed:
    blocks = []

    if summary.get("commands_added"):
        blocks.append("**🆕 Se agregaron comandos**\n" + "\n".join(_command_line(command) for command in summary["commands_added"]))
    if summary.get("commands_removed"):
        blocks.append("**🗑️ Se retiraron comandos**\n" + "\n".join(_command_line(command) for command in summary["commands_removed"]))
    if summary.get("commands_updated"):
        blocks.append("**✏️ Se modificaron comandos**\n" + "\n".join(_command_line(command) for command in summary["commands_updated"]))

    if summary["notes"]:
        lines = [_change_line(note) for note in summary["notes"][:MAX_COMMITS_SHOWN]]
        if len(summary["notes"]) > MAX_COMMITS_SHOWN:
            lines.append(f"• Y {len(summary['notes']) - MAX_COMMITS_SHOWN} cambios más")
        blocks.append("**Qué se hizo**\n" + "\n".join(lines))

    if not blocks:
        areas = sorted({FILE_LABELS.get(path.rsplit("/", 1)[-1], path.rsplit("/", 1)[-1]) for path in summary["added"] + summary["modified"] + summary["removed"]})
        blocks.append("**Áreas actualizadas**\n" + "\n".join(f"• {area}" for area in areas) if areas else "Se publicaron cambios en el bot.")
    if summary["compare"]:
        blocks.append(f"[Ver los cambios en GitHub]({summary['compare']})")

    embed = discord.Embed(title="🔧 Actualización del bot", description="\n\n".join(blocks)[:4000], color=COLOR)
    embed.timestamp = discord.utils.utcnow()
    return embed


SAMPLE_PAYLOAD = {
    "ref": "refs/heads/main",
    "repository": {"full_name": "tu-usuario/tu-repo"},
    "pusher": {"name": "tú"},
    "compare": "",
    "commits": [{
        "message": "feat: agrega el comando ,wlc\nPermite configurar el canal y el mensaje de bienvenida desde Discord.",
        "author": {"name": "tú"},
        "added": ["wlc.py"], "modified": ["help.py", "main.py"], "removed": [],
    }],
}


# ── Cog ──────────────────────────────────────────────────────────────────────

class GithubUpdates(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner = None
        self.started_at = time.monotonic()
        self.deliveries: list = []          # ids de entregas ya procesadas (GitHub reintenta si tarda)
        self.last_event = None
        self.oauth_states = {}
        self.web_sessions = {}

    async def cog_load(self):
        app = web.Application(client_max_size=MAX_BODY_BYTES)
        app.router.add_get("/", self.website)
        app.router.add_get("/animejs.min.js", self.animejs_asset)
        app.router.add_get("/health", self.health)
        app.router.add_get("/api/status", self.public_status)
        app.router.add_get("/api/commands", self.public_commands)
        app.router.add_get("/api/auth/config", self.auth_config)
        app.router.add_get("/api/auth/discord", self.auth_discord)
        app.router.add_get("/api/auth/callback", self.auth_callback)
        app.router.add_get("/api/auth/me", self.auth_me)
        app.router.add_post("/api/auth/logout", self.auth_logout)
        app.router.add_get("/api/discord/guilds", self.discord_guilds)
        app.router.add_get("/api/discord/guilds/{guild_id}/channels", self.discord_channels)
        app.router.add_post("/api/discord/send-embed", self.send_embed)
        if SECRET:
            app.router.add_post("/github", self.handle_github)
        else:
            log.warning("GITHUB_WEBHOOK_SECRET no está configurada: webhook de GitHub apagado; la web seguirá disponible")
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "0.0.0.0", PORT).start()
        log.info(f"Web y API escuchando en el puerto {PORT}" + (f"; webhook de GitHub activo para '{BRANCH}'" if SECRET else ""))

    async def cog_unload(self):
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    # ── Servidor web ─────────────────────────────────────────────────────────

    async def health(self, request):
        return web.Response(text="ok")

    async def website(self, request):
        return web.FileResponse(WEBSITE_DIR / "index.html")

    async def animejs_asset(self, request):
        return web.FileResponse(
            WEBSITE_DIR / "vendor-animejs-4.5.0.js",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    async def public_status(self, request):
        user = self.bot.user
        ready = self.bot.is_ready() and user is not None
        payload = {
            "online": ready,
            "name": user.name if user else "Zaay",
            "avatar": user.display_avatar.url if user else None,
            "guilds": len(self.bot.guilds) if ready else 0,
            "members": sum(guild.member_count or 0 for guild in self.bot.guilds) if ready else 0,
            "latency_ms": round(self.bot.latency * 1000) if ready else None,
            "uptime_seconds": int(time.monotonic() - self.started_at),
            "checked_at": int(time.time()),
        }
        return web.json_response(payload, headers={"Cache-Control": "no-store"})

    async def public_commands(self, request):
        from help import CATEGORIES, HIDDEN_CATEGORIES
        from cmd_help import COMMAND_INFO

        categories = []
        for key, data in CATEGORIES.items():
            if key in HIDDEN_CATEGORIES:
                continue
            sections = []
            for title, commands, note in data["sections"]:
                items = []
                for syntax in commands:
                    raw_name = syntax.split(" — ", 1)[0].split(" / ", 1)[0].strip().lstrip(",")
                    name = re.split(r"\s+(?=[<\[])", raw_name, maxsplit=1)[0].strip()
                    command = self.bot.get_command(name)
                    info = COMMAND_INFO.get(name, {})
                    description = info.get("desc") or (command.short_doc or command.help or "").split("\n", 1)[0].strip() if command else info.get("desc", "")
                    items.append({"name": name, "syntax": syntax, "description": description})
                sections.append({"title": title, "items": items, "note": note})
            categories.append({"id": key, "name": data["label"], "description": data["description"], "sections": sections})
        return web.json_response({"prefix": ",", "categories": categories}, headers={"Cache-Control": "no-store"})

    def _session(self, request):
        session_id = request.cookies.get("zaay_session", "")
        session = self.web_sessions.get(session_id)
        if not session or session["expires_at"] <= time.time():
            self.web_sessions.pop(session_id, None)
            return None
        return session

    async def _discord_request(self, method, path, *, token=None, data=None):
        headers = {"Authorization": f"Bot {self.bot.http.token}"} if token is None else {"Authorization": f"Bearer {token}"}
        async with ClientSession(timeout=ClientTimeout(total=12)) as session:
            async with session.request(method, f"{DISCORD_API}{path}", headers=headers, data=data) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    raise web.HTTPBadGateway(text="Discord no pudo completar la solicitud.")
                return payload

    async def auth_config(self, request):
        return web.json_response({"configured": bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET), "redirect_uri": DISCORD_REDIRECT_URI})

    async def auth_discord(self, request):
        if not DISCORD_CLIENT_SECRET:
            raise web.HTTPServiceUnavailable(text="Falta configurar DISCORD_CLIENT_SECRET en Railway.")
        for state, created in list(self.oauth_states.items()):
            if created < time.time() - 600:
                self.oauth_states.pop(state, None)
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = time.time()
        params = urlencode({
            "client_id": DISCORD_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": DISCORD_REDIRECT_URI,
            "scope": "identify guilds",
        })
        raise web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}&state={state}")

    async def auth_callback(self, request):
        state = request.query.get("state", "")
        created = self.oauth_states.pop(state, None)
        if not created or created < time.time() - 600 or request.query.get("iss") not in (None, "https://discord.com"):
            raise web.HTTPFound("/#/embed-builder?oauth_error=state")
        code = request.query.get("code")
        if not code or not DISCORD_CLIENT_SECRET:
            raise web.HTTPFound("/#/embed-builder?oauth_error=config")
        form = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }
        try:
            async with ClientSession(timeout=ClientTimeout(total=12)) as session:
                async with session.post(f"{DISCORD_API}/oauth2/token", data=form) as response:
                    token_data = await response.json(content_type=None)
            if "access_token" not in token_data:
                raise ValueError("Discord no devolvió token")
            user = await self._discord_request("GET", "/users/@me", token=token_data["access_token"])
        except (ClientError, asyncio.TimeoutError, ValueError, KeyError):
            log.warning("Falló el inicio de sesión OAuth de Discord", exc_info=True)
            raise web.HTTPFound("/#/embed-builder?oauth_error=exchange")

        session_id = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        lifetime = min(int(token_data.get("expires_in", 3600)), 604800)
        self.web_sessions[session_id] = {
            "token": token_data["access_token"],
            "expires_at": time.time() + lifetime,
            "user_id": user["id"],
            "username": user.get("global_name") or user.get("username", "Discord"),
            "avatar": user.get("avatar"),
            "csrf": csrf,
        }
        response = web.HTTPFound("/#/embed-builder?connected=1")
        response.set_cookie("zaay_session", session_id, max_age=lifetime, httponly=True, secure=True, samesite="Lax", path="/")
        return response

    async def auth_me(self, request):
        session = self._session(request)
        if not session:
            return web.json_response({"authenticated": False})
        return web.json_response({"authenticated": True, "user": {"id": session["user_id"], "name": session["username"], "avatar": session["avatar"]}, "csrf": session["csrf"]}, headers={"Cache-Control": "no-store"})

    async def auth_logout(self, request):
        session = self._session(request)
        if session and request.headers.get("X-CSRF-Token") != session["csrf"]:
            raise web.HTTPForbidden(text="Solicitud no válida.")
        session_id = request.cookies.get("zaay_session", "")
        self.web_sessions.pop(session_id, None)
        response = web.json_response({"ok": True})
        response.del_cookie("zaay_session", path="/")
        return response

    async def discord_guilds(self, request):
        session = self._session(request)
        if not session:
            raise web.HTTPUnauthorized(text="Inicia sesión con Discord para continuar.")
        user_guilds = await self._discord_request("GET", "/users/@me/guilds", token=session["token"])
        bot_guild_ids = {str(guild.id) for guild in self.bot.guilds}
        manageable = []
        for guild in user_guilds:
            permissions = int(guild.get("permissions", "0"))
            if guild["id"] not in bot_guild_ids or not permissions & ((1 << 5) | (1 << 3)):
                continue
            icon = guild.get("icon")
            manageable.append({"id": guild["id"], "name": guild["name"], "icon": f"https://cdn.discordapp.com/icons/{guild['id']}/{icon}.png?size=64" if icon else None})
        return web.json_response({"guilds": manageable}, headers={"Cache-Control": "no-store"})

    async def discord_channels(self, request):
        session = self._session(request)
        if not session:
            raise web.HTTPUnauthorized(text="Inicia sesión con Discord para continuar.")
        guild_id = request.match_info["guild_id"]
        user_guilds = await self._discord_request("GET", "/users/@me/guilds", token=session["token"])
        authorized = any(g["id"] == guild_id and int(g.get("permissions", "0")) & ((1 << 5) | (1 << 3)) for g in user_guilds)
        guild = self.bot.get_guild(int(guild_id)) if guild_id.isdecimal() else None
        if not authorized or not guild:
            raise web.HTTPForbidden(text="No tienes acceso a ese servidor o Zaay no está dentro.")
        channels = []
        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.send_messages and permissions.embed_links:
                channels.append({"id": str(channel.id), "name": channel.name, "category": channel.category.name if channel.category else ""})
        return web.json_response({"channels": channels}, headers={"Cache-Control": "no-store"})

    async def send_embed(self, request):
        session = self._session(request)
        if not session:
            raise web.HTTPUnauthorized(text="Inicia sesión con Discord para continuar.")
        origin = request.headers.get("Origin", "")
        expected_origin = DISCORD_REDIRECT_URI.removesuffix("/api/auth/callback")
        if origin != expected_origin or request.headers.get("X-CSRF-Token") != session["csrf"]:
            raise web.HTTPForbidden(text="Solicitud no válida.")
        try:
            payload = await request.json()
            guild_id = int(payload["guild_id"])
            channel_id = int(payload["channel_id"])
            embed_data = payload["embed"]
            content = payload.get("content", "")
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest(text="Falta seleccionar servidor, canal o contenido.")
        if not isinstance(content, str) or len(content) > 2000:
            raise web.HTTPBadRequest(text="El texto fuera del embed debe tener 2,000 caracteres o menos.")
        user_guilds = await self._discord_request("GET", "/users/@me/guilds", token=session["token"])
        authorized = any(g["id"] == str(guild_id) and int(g.get("permissions", "0")) & ((1 << 5) | (1 << 3)) for g in user_guilds)
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if not authorized or not isinstance(channel, discord.TextChannel):
            raise web.HTTPForbidden(text="No tienes permiso para publicar en ese servidor.")
        permissions = channel.permissions_for(guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            raise web.HTTPForbidden(text="Zaay necesita permiso para enviar mensajes y embeds en ese canal.")
        if not isinstance(embed_data, dict) or set(embed_data) - {"title", "description", "url", "color", "timestamp", "author", "thumbnail", "image", "footer", "fields"}:
            raise web.HTTPBadRequest(text="El formato del embed no es válido.")
        try:
            embed = discord.Embed.from_dict(embed_data)
            if not embed.title and not embed.description and not embed.fields and not embed.author.name and not embed.image.url and not embed.thumbnail.url:
                raise ValueError("empty embed")
            await channel.send(content=content or None, embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, ValueError, TypeError):
            raise web.HTTPBadRequest(text="Discord rechazó el embed. Revisa los campos y sus límites.")
        return web.json_response({"ok": True})

    async def handle_github(self, request):
        body = await request.read()
        if not verify_signature(SECRET, body, request.headers.get("X-Hub-Signature-256")):
            return web.Response(status=401, text="firma inválida")

        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return web.Response(text="pong")
        if event != "push":
            return web.Response(status=202, text="ignorado")

        delivery = request.headers.get("X-GitHub-Delivery")
        if delivery and delivery in self.deliveries:
            return web.Response(text="repetido")
        if delivery:
            self.deliveries = (self.deliveries + [delivery])[-50:]

        try:
            payload = json.loads(body)
        except ValueError:
            return web.Response(status=400, text="JSON inválido")

        asyncio.create_task(self.process_push(payload))   # se responde rápido a GitHub
        return web.Response(status=202, text="ok")

    # ── Anuncio ──────────────────────────────────────────────────────────────

    def _target(self):
        state = db.get(STATE_KEY, None) or {}
        if state.get("enabled") is False:
            return None
        channel_id = state.get("channel_id") or os.getenv("UPDATES_CHANNEL_ID")
        try:
            return int(channel_id) if channel_id else None
        except (TypeError, ValueError):
            return None

    async def process_push(self, payload: dict):
        try:
            self.last_event = time.time()
            if payload.get("deleted") or payload.get("ref") != f"refs/heads/{BRANCH}":
                return
            summary = summarize_push(payload)
            if not summary["commit_count"]:
                return
            summary["commands_added"], summary["commands_removed"], summary["commands_updated"] = await _commands_from_github_compare(payload)
            await self.announce(summary)
        except Exception:
            log.exception("Falló el anuncio de la actualización")

    async def announce(self, summary: dict) -> bool:
        channel_id = await asyncio.to_thread(self._target)
        if channel_id is None:
            log.warning("Llegó una actualización de GitHub pero no hay canal configurado (usa ,updates channel)")
            return False
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning(f"No pude encontrar el canal de actualizaciones {channel_id}")
                return False
        try:
            await channel.send(embed=build_announcement(summary), allowed_mentions=discord.AllowedMentions.none())
            return True
        except discord.HTTPException:
            log.warning("No pude escribir en el canal de actualizaciones (¿permisos?)")
            return False

    # ── Comandos ─────────────────────────────────────────────────────────────

    @commands.group(name="updates", invoke_without_command=True)
    @commands.is_owner()
    async def updates(self, ctx: commands.Context):
        from cmd_help import build_command_card
        await ctx.send(embed=build_command_card(ctx))

    @updates.command(name="channel")
    async def updates_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        db.set(STATE_KEY, {"guild_id": channel.guild.id, "channel_id": channel.id, "enabled": True})
        await success(ctx, f"Anunciaré las actualizaciones del bot en {channel.mention} ({channel.guild.name}).")

    @updates.command(name="off")
    async def updates_off(self, ctx: commands.Context):
        state = db.get(STATE_KEY, None) or {}
        state["enabled"] = False
        db.set(STATE_KEY, state)
        await success(ctx, "Dejé de anunciar las actualizaciones. Usa `updates channel` para volver a activarlas.")

    @updates.command(name="status")
    async def updates_status(self, ctx: commands.Context):
        channel_id = self._target()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        lines = [
            f"**Canal:** {channel.mention if channel else ('`' + str(channel_id) + '` (no lo encuentro)' if channel_id else 'sin configurar')}",
            f"**Rama:** `{BRANCH}`",
            f"**Clave secreta (`GITHUB_WEBHOOK_SECRET`):** {'configurada' if SECRET else 'FALTA — el servidor de avisos está apagado'}",
            f"**Servidor de avisos:** {'activo en el puerto ' + str(PORT) if self.runner else 'apagado'}",
            "**Último aviso de GitHub:** " + (f"<t:{int(self.last_event)}:R>" if self.last_event else "ninguno desde que arrancó el bot"),
        ]
        await ctx.send(embed=discord.Embed(title="Anuncios de actualizaciones", description="\n".join(lines), color=COLOR))

    @updates.command(name="test")
    async def updates_test(self, ctx: commands.Context):
        summary = summarize_push(SAMPLE_PAYLOAD)
        summary["commands_added"] = [{"name": "wlc", "kind": "prefix", "area": "Bienvenidas"}]
        if await self.announce(summary):
            await success(ctx, "Mandé un anuncio de prueba al canal configurado.")
        else:
            await error(ctx, "No pude mandarlo. Configura el canal con `updates channel` y revisa que tenga permisos de escritura.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GithubUpdates(bot))


