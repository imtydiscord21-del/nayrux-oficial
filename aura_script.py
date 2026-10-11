"""
aura_script.py — Motor de mensajes con la sintaxis de etiquetas  {tag: valor}.

Se usa en ,wlc config (bienvenida) y ,boostmsg config / unboostconfig (boosts).

SINTAXIS
  texto plano                 -> mensaje normal:   ,wlc config #bienvenida hola {user.mention}
  {content: texto}            -> contenido del mensaje (fuera del embed)
  {embed}                     -> indica que hay un embed
  {embed:nombre}              -> usa un embed guardado con ,embed create
  {title: texto}              {description: texto}      {color: #hex}
  {thumbnail: url}            {image: url}              {timestamp}
  {footer: text: texto && icon: url}
  {author: name: texto && icon: url}
  {field: name: texto && value: texto && inline: true}
  {button: label: texto && url: enlace && emoji: emoji}     (botón de enlace; máx. 5)

VARIABLES
  {user} {user.name} {user.display} {user.id} {user.avatar} {user.mention} {user.color}
  {user.created_at} {user.joined_at}
  {guild.name} {guild.id} {guild.icon} {guild.count} {guild.boost_count} {guild.boost_level}

Las variables se reemplazan primero y sus valores se "blindan" (las llaves del valor no se
interpretan como etiquetas), así que un nombre de usuario con "{" no rompe el mensaje.
"""

import re
from dataclasses import dataclass, field

import discord

# Marcadores privados para blindar llaves que vienen DENTRO de un valor sustituido
_OPEN = "\ue000"
_CLOSE = "\ue001"

EMBED_TAGS = {"title", "description", "color", "thumbnail", "image", "footer", "author", "field", "timestamp"}
KNOWN_TAGS = EMBED_TAGS | {"content", "embed", "button"}

MAX_BUTTONS = 5
MAX_FIELDS = 25

# Textos de la documentación (usados por ,wlc variables / ,boostmsg variables)
USER_VARIABLES = [
    ("{user}", "Mención"),
    ("{user.name}", "Nombre de usuario"),
    ("{user.display}", "Nombre para mostrar"),
    ("{user.id}", "ID"),
    ("{user.avatar}", "URL del avatar"),
    ("{user.mention}", "Mención"),
    ("{user.color}", "Color hex"),
    ("{user.created_at}", "Fecha de creación"),
    ("{user.joined_at}", "Fecha de ingreso"),
]
GUILD_VARIABLES = [
    ("{guild.name}", "Nombre del servidor"),
    ("{guild.id}", "ID del servidor"),
    ("{guild.icon}", "URL del ícono"),
    ("{guild.count}", "Cantidad de miembros"),
    ("{guild.boost_count}", "Cantidad de boosts"),
]
GUILD_VARIABLES_BOOST = GUILD_VARIABLES + [("{guild.boost_level}", "Nivel de boost")]

FORMAT_TAGS = [
    ("{content: texto}", "Contenido del mensaje"),
    ("{description: texto}", "Descripción del embed"),
    ("{title: texto}", "Título del embed"),
    ("{footer: text: texto && icon: url}", "Pie"),
    ("{author: name: texto && icon: url}", "Autor"),
    ("{thumbnail: url}", "Miniatura"),
    ("{image: url}", "Imagen"),
    ("{color: hex}", "Color"),
    ("{timestamp}", "Fecha y hora"),
    ("{field: name: texto && value: texto && inline: true}", "Campo"),
]
BUTTON_TAGS = [
    ("{button: label: texto && url: enlace && emoji: emoji}", "Agrega un botón"),
    ("{button: label: Beneficios && url: https://ejemplo.com && emoji: 🎁}", None),
]


# ── Variables ────────────────────────────────────────────────────────────────

def _protect(value) -> str:
    return str(value).replace("{", _OPEN).replace("}", _CLOSE)


def _restore(text: str) -> str:
    return text.replace(_OPEN, "{").replace(_CLOSE, "}")


def variable_values(member: discord.Member, guild: discord.Guild | None = None) -> dict:
    guild = guild or member.guild
    joined = getattr(member, "joined_at", None)
    return {
        "{user}": member.mention,
        "{user.name}": member.name,
        "{user.display}": member.display_name,
        "{user.id}": member.id,
        "{user.avatar}": member.display_avatar.url,
        "{user.mention}": member.mention,
        "{user.color}": str(member.color) if hasattr(member, "color") else "#000000",
        "{user.created_at}": discord.utils.format_dt(member.created_at, "D"),
        "{user.joined_at}": discord.utils.format_dt(joined, "D") if joined else "—",
        "{guild.name}": guild.name,
        "{guild.id}": guild.id,
        "{guild.icon}": guild.icon.url if guild.icon else "",
        "{guild.count}": guild.member_count or 0,
        "{guild.boost_count}": guild.premium_subscription_count or 0,
        "{guild.boost_level}": guild.premium_tier,
    }


def substitute(text: str, values: dict) -> str:
    # Primero los nombres más largos, para que {user.name} no lo pise {user}
    for key in sorted(values, key=len, reverse=True):
        text = text.replace(key, _protect(values[key]))
    return text


# ── Lectura de etiquetas ─────────────────────────────────────────────────────

def split_blocks(text: str):
    """
    Parte el texto en [("text", str) | ("tag", str)]. Una etiqueta es un bloque {...} de nivel
    superior (con llaves anidadas permitidas). Devuelve también si quedó alguna llave sin cerrar.
    """
    parts, buf, depth, start, unbalanced = [], [], 0, 0, False
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                if buf:
                    parts.append(("text", "".join(buf)))
                    buf = []
                start = i + 1
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                parts.append(("tag", text[start:i]))
        elif depth == 0:
            buf.append(ch)
    if depth > 0:
        unbalanced = True
    elif buf:
        parts.append(("text", "".join(buf)))
    return parts, unbalanced


def parse_params(value: str) -> dict:
    """'text: hola && icon: https://x' -> {'text': 'hola', 'icon': 'https://x'}."""
    out = {}
    for part in value.split("&&"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, val = part.split(":", 1)
            key = key.strip().lower()
            if re.fullmatch(r"[a-z_]+", key):
                out[key] = val.strip()
                continue
        out.setdefault("_", part)
    return out


def _color(value: str):
    value = value.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return int(value, 16)
    return None


def _is_url(value: str) -> bool:
    return bool(re.match(r"^https?://\S+$", value or ""))


# ── Resultado ────────────────────────────────────────────────────────────────

@dataclass
class Script:
    content: str = ""
    has_embed: bool = False
    custom_embed: str | None = None
    title: str | None = None
    description: str | None = None
    color: int | None = None
    thumbnail: str | None = None
    image: str | None = None
    footer_text: str | None = None
    footer_icon: str | None = None
    author_name: str | None = None
    author_icon: str | None = None
    timestamp: bool = False
    fields: list = field(default_factory=list)       # [(name, value, inline)]
    buttons: list = field(default_factory=list)      # [{"label","url","emoji"}]
    errors: list = field(default_factory=list)       # problemas de sintaxis

    @property
    def is_empty(self) -> bool:
        return not (self.content.strip() or self.has_embed or self.custom_embed or self.buttons)


def parse(text: str) -> Script:
    """Lee un mensaje escrito con la sintaxis {tag: valor}. No necesita Discord."""
    script = Script()
    parts, unbalanced = split_blocks(text)
    if unbalanced:
        script.errors.append("Falta una `}` de cierre en alguna etiqueta.")

    plain = []
    content_tags = []
    for kind, raw in parts:
        if kind == "text":
            plain.append(raw)
            continue

        key, _, value = raw.partition(":")
        key_l = key.strip().lower()
        value = value.strip()

        if key_l not in KNOWN_TAGS:
            # No es una etiqueta conocida: se deja como texto, tal cual lo escribió el usuario
            plain.append("{" + raw + "}")
            if re.fullmatch(r"[a-z_]+", key_l) and not key_l.startswith(("user", "guild")):
                script.errors.append(f"No reconozco la etiqueta `{{{key_l}}}`.")
            continue

        if key_l == "content":
            content_tags.append(value)
        elif key_l == "embed":
            script.has_embed = True
            if value:
                script.custom_embed = value
        elif key_l in EMBED_TAGS:
            script.has_embed = True
            if key_l == "title":
                script.title = value
            elif key_l == "description":
                script.description = f"{script.description}\n{value}" if script.description else value
            elif key_l == "color":
                col = _color(value)
                if col is None:
                    script.errors.append(f"El color `{value}` no es válido; usa un hex como `#5865f2`.")
                else:
                    script.color = col
            elif key_l == "thumbnail":
                if _is_url(value):
                    script.thumbnail = value
                elif value:
                    script.errors.append("La miniatura debe ser una URL (`http...`).")
            elif key_l == "image":
                if _is_url(value):
                    script.image = value
                elif value:
                    script.errors.append("La imagen debe ser una URL (`http...`).")
            elif key_l == "timestamp":
                script.timestamp = True
            elif key_l == "footer":
                p = parse_params(value)
                script.footer_text = p.get("text") or p.get("_")
                script.footer_icon = p.get("icon") if _is_url(p.get("icon", "")) else None
            elif key_l == "author":
                p = parse_params(value)
                script.author_name = p.get("name") or p.get("_")
                script.author_icon = p.get("icon") if _is_url(p.get("icon", "")) else None
            elif key_l == "field":
                p = parse_params(value)
                name, val = p.get("name"), p.get("value")
                if not name or not val:
                    script.errors.append("Un `{field: ...}` necesita `name:` y `value:`.")
                elif len(script.fields) >= MAX_FIELDS:
                    script.errors.append(f"Un embed admite como máximo {MAX_FIELDS} campos.")
                else:
                    script.fields.append((name, val, p.get("inline", "false").lower() in ("true", "yes", "si", "sí", "on")))
        elif key_l == "button":
            p = parse_params(value)
            label, url = p.get("label"), p.get("url")
            if not label or not _is_url(url or ""):
                script.errors.append("Un `{button: ...}` necesita `label:` y un `url:` que empiece con http.")
            elif len(script.buttons) >= MAX_BUTTONS:
                script.errors.append(f"Se admiten como máximo {MAX_BUTTONS} botones.")
            else:
                script.buttons.append({"label": label[:80], "url": url, "emoji": p.get("emoji")})

    leftover = "".join(plain).strip()
    pieces = [p for p in (leftover, *content_tags) if p]
    script.content = "\n".join(pieces)[:2000]
    return script


def render_text(text: str, member: discord.Member, guild: discord.Guild | None = None) -> str:
    """Reemplaza las variables y deja el texto listo para parse()."""
    return substitute(text, variable_values(member, guild))


# ── Construcción del mensaje de Discord ──────────────────────────────────────

def _cut(text, limit):
    if text is None:
        return None
    text = _restore(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_embed(script: Script) -> discord.Embed | None:
    if not script.has_embed:
        return None
    e = discord.Embed(color=script.color if script.color is not None else 0x2B2D31)
    if script.title:
        e.title = _cut(script.title, 256)
    if script.description:
        e.description = _cut(script.description, 4096)
    if script.author_name:
        e.set_author(name=_cut(script.author_name, 256), icon_url=script.author_icon)
    if script.footer_text:
        e.set_footer(text=_cut(script.footer_text, 2048), icon_url=script.footer_icon)
    if script.thumbnail:
        e.set_thumbnail(url=_restore(script.thumbnail))
    if script.image:
        e.set_image(url=_restore(script.image))
    for name, value, inline in script.fields:
        e.add_field(name=_cut(name, 256), value=_cut(value, 1024), inline=inline)
    if script.timestamp:
        e.timestamp = discord.utils.utcnow()
    return e


def build_view(script: Script) -> discord.ui.View | None:
    if not script.buttons:
        return None
    view = discord.ui.View()
    for b in script.buttons:
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=_restore(b["label"]),
            url=_restore(b["url"]),
            emoji=b.get("emoji") or None,
        ))
    return view


def build_message(text: str, member: discord.Member, guild: discord.Guild | None = None, loader=None):
    """
    Texto con etiquetas -> (content, embed, view, errores).
    loader(nombre) debe devolver el texto de un embed guardado (para {embed:nombre}) o None.
    """
    script = parse(render_text(text, member, guild))
    errors = list(script.errors)

    if script.custom_embed:
        saved = loader(script.custom_embed) if loader else None
        if saved is None:
            errors.append(f"No existe un embed guardado llamado `{script.custom_embed}`. Créalo con `,embed create`.")
        else:
            inner = parse(render_text(saved, member, guild))
            errors.extend(inner.errors)
            # El embed guardado aporta su aspecto; lo escrito en el mensaje tiene prioridad
            for attr in ("title", "description", "color", "thumbnail", "image", "footer_text", "footer_icon",
                         "author_name", "author_icon"):
                if getattr(script, attr) is None:
                    setattr(script, attr, getattr(inner, attr))
            script.timestamp = script.timestamp or inner.timestamp
            script.fields = script.fields or inner.fields
            script.buttons = script.buttons or inner.buttons
            if inner.content and not script.content:
                script.content = inner.content
            script.has_embed = script.has_embed or inner.has_embed

    content = _restore(script.content) if script.content else None
    return content, build_embed(script), build_view(script), errors


def validate(text: str):
    """
    Revisa un mensaje tal como lo escribió quien configura (con las variables SIN reemplazar).
    Devuelve la lista de problemas; vacía si está bien.
    """
    # Variables ficticias para poder leer la estructura
    url_vars = {"{user.avatar}", "{guild.icon}"}
    placeholder = {k: ("https://example.com/a.png" if k in url_vars else "x") for k in variable_values_keys()}
    script = parse(substitute(text, placeholder))
    problems = list(script.errors)
    if script.is_empty:
        problems.append("El mensaje está vacío.")
    return problems


def variable_values_keys():
    return [k for k, _ in USER_VARIABLES + GUILD_VARIABLES_BOOST]
