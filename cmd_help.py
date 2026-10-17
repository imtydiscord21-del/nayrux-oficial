"""
cmd_help.py — Tarjeta de ayuda de un comando (estilo bleed, en español).

Se usa en dos sitios:
  - main.py: cuando a un comando le falta un argumento.
  - help.py: ,help <comando>

La tarjeta muestra el nombre, una descripción en negrita, la sintaxis/ejemplo en un bloque de
código, los subcomandos (si es un grupo) y los permisos que pide el comando.
"""

import discord
from discord.ext import commands

from config import db, DEFAULT_PREFIX

# desc    -> descripción corta (se muestra en negrita)
# syntax  -> (opcional) sintaxis exacta sin el prefijo; si falta se arma sola
# example -> ejemplo sin el prefijo
COMMAND_INFO = {
    "ban": {"desc": "Banea al usuario mencionado", "syntax": "ban (usuario) (razón)", "example": "ban derek spam"},
    "kick": {"desc": "Expulsa al usuario mencionado del servidor", "syntax": "kick (miembro) <razón>", "example": "kick derek Necesitas un descanso"},
    "jail": {"desc": "Aísla a un miembro quitándole el acceso a los canales", "example": "jail @usuario revisando el caso"},
    "timeout": {"desc": "Silencia a un miembro por un tiempo determinado", "example": "timeout @usuario 10m spameando"},
    "warn": {"desc": "Advierte a un miembro", "example": "warn @usuario lenguaje inapropiado"},
    "purge": {"desc": "Borra una cantidad de mensajes del canal", "example": "purge 50"},
    "role add": {"desc": "Agrega un rol a un miembro", "example": "role add @usuario Miembro"},
    "role remove": {"desc": "Quita un rol a un miembro", "example": "role remove @usuario Miembro"},
    "r": {"desc": "Agrega el rol si no lo tiene, lo quita si ya lo tiene", "example": "r @usuario Miembro"},
    "lock": {"desc": "Bloquea el canal actual (o el que indiques)", "example": "lock"},
    "unlock": {"desc": "Desbloquea el canal", "example": "unlock"},
    "slowmode": {"desc": "Configura el modo lento del canal", "example": "slowmode 10"},
    "nickname": {"desc": "Cambia el apodo de un miembro", "example": "nickname @usuario Nuevo Nombre"},
    "unban": {"desc": "Desbanea a un usuario por su ID", "example": "unban 123456789012345678"},
    "hardban": {"desc": "Banea a un usuario y lo vuelve a banear si alguien lo desbanea. Usa el mismo comando otra vez para quitarle el hardban", "example": "hb 123456789012345678 haciendo alts"},
    "rolesoff": {"desc": "Quita todos los permisos a todos los roles del servidor y guarda una copia (solo dueño del bot/servidor)", "example": "rolesoff"},
    "roleson": {"desc": "Restaura los permisos guardados por ,rolesoff a todos los roles (solo dueño del bot/servidor)", "example": "roleson"},
    "ai": {"desc": "Consulta a la IA", "example": "ai explícame qué es un webhook"},
    "ai setup": {"desc": "Activa la IA en un canal", "example": "ai setup #general"},
    "ai off": {"desc": "Desactiva el canal de IA", "example": "ai off"},
    "ai status": {"desc": "Muestra la configuración de la IA", "example": "ai status"},
    "ai persona": {"desc": "Cambia la personalidad de la IA", "example": "ai persona Eres un pirata"},
    "ai reset": {"desc": "Borra el historial del canal actual", "example": "ai reset"},
    "ai clearhistory": {"desc": "Borra el historial de todos los canales", "example": "ai clearhistory"},
    "fakepermissions": {"desc": "Configura permisos falsos: tus moderadores usan los comandos del bot sin tener el permiso real de Discord", "syntax": "fakepermissions (subcomando)", "example": "fakepermissions add @admin ban_members, kick_members"},
    "fakepermissions add": {"desc": "Otorga permisos falsos a un rol", "syntax": "fakepermissions add (rol) (permisos)", "example": "fakepermissions add @admin ban_members, kick_members"},
    "fakepermissions remove": {"desc": "Quita permisos falsos a un rol", "syntax": "fakepermissions remove (rol) (permisos)", "example": "fakepermissions remove @admin ban_members, kick_members"},
    "fakepermissions list": {"desc": "Muestra los permisos falsos configurados", "syntax": "fakepermissions list <rol>", "example": "fakepermissions list @admin"},
    "fakepermissions reset": {"desc": "Restablece todos los permisos falsos", "example": "fakepermissions reset"},
    "instagram": {"desc": "Recibe notificaciones cuando una cuenta de Instagram publica", "syntax": "instagram (subcomando)", "example": "instagram add #notifs playboicarti"},
    "instagram add": {"desc": "Recibe las publicaciones de una cuenta de Instagram en un canal", "syntax": "instagram add (canal) (usuario)", "example": "instagram add #notifs playboicarti"},
    "instagram remove": {"desc": "Deja de recibir las publicaciones de una cuenta en un canal", "syntax": "instagram remove (canal) (usuario)", "example": "instagram remove #notifs playboicarti"},
    "instagram message": {"desc": "Personaliza el mensaje que acompaña cada notificación", "syntax": "instagram message (usuario) (mensaje) <--pingable on|off>", "example": "instagram message playboicarti @everyone ¿publicó?? --pingable on"},
    "instagram list": {"desc": "Muestra las cuentas de Instagram que se están monitoreando", "example": "instagram list"},
    "vanityclaim": {"desc": "Reclama sola una vanity para tu servidor cuando se libere", "syntax": "vanityclaim (subcomando)", "example": "vanityclaim add mivanity"},
    "vanityclaim add": {"desc": "Empieza a vigilar una vanity y la reclama en cuanto esté libre", "syntax": "vanityclaim add (código)", "example": "vanityclaim add mivanity"},
    "vanityclaim remove": {"desc": "Deja de vigilar una vanity", "syntax": "vanityclaim remove (código)", "example": "vanityclaim remove mivanity"},
    "vanityclaim list": {"desc": "Muestra las vanities que se están vigilando", "example": "vanityclaim list"},
    "vanityclaim channel": {"desc": "Canal donde avisa al reclamar una vanity", "syntax": "vanityclaim channel (canal)", "example": "vanityclaim channel #avisos"},
    "vanityclaim check": {"desc": "Revisa ahora mismo si una vanity está libre", "syntax": "vanityclaim check (código)", "example": "vanityclaim check mivanity"},
    "updates": {"desc": "Anuncia en un canal cada actualización que subas a GitHub", "syntax": "updates (subcomando)", "example": "updates channel #actualizaciones"},
    "updates channel": {"desc": "Define el canal donde se anuncian las actualizaciones del bot", "syntax": "updates channel (canal)", "example": "updates channel #actualizaciones"},
    "updates status": {"desc": "Muestra la configuración de los anuncios de actualizaciones", "example": "updates status"},
    "updates test": {"desc": "Manda un anuncio de prueba al canal configurado", "example": "updates test"},
    "updates off": {"desc": "Deja de anunciar las actualizaciones", "example": "updates off"},
    "wlc": {"desc": "Configura el mensaje de bienvenida", "syntax": "wlc (subcomando)", "example": "wlc config #bienvenida bienvenido {user.mention}!"},
    "wlc config": {"desc": "Define el canal y el mensaje de bienvenida", "syntax": "wlc config (canal) (mensaje)", "example": "wlc config #bienvenida bienvenido {user.mention} al servidor!"},
    "wlc test": {"desc": "Muestra cómo se vería el mensaje de bienvenida", "example": "wlc test"},
    "wlc variables": {"desc": "Muestra las variables y etiquetas disponibles", "example": "wlc variables"},
    "wlc templates": {"desc": "Muestra plantillas listas para copiar", "example": "wlc templates"},
    "wlc reset": {"desc": "Borra la configuración de bienvenida", "example": "wlc reset"},
    "boostmsg": {"desc": "Configura los mensajes de boost y unboost", "syntax": "boostmsg (subcomando)", "example": "boostmsg config #boosts gracias {user.mention}!"},
    "boostmsg config": {"desc": "Define el canal y el mensaje cuando alguien boostea", "syntax": "boostmsg config (canal) (mensaje)", "example": "boostmsg config #boosts gracias {user.mention} por boostear!"},
    "boostmsg unboostconfig": {"desc": "Define el canal y el mensaje cuando alguien deja de boostear", "syntax": "boostmsg unboostconfig (canal) (mensaje)", "example": "boostmsg unboostconfig #boosts {user.display} dejó de boostear"},
    "boostmsg test": {"desc": "Muestra cómo se vería el mensaje de boost", "example": "boostmsg test"},
    "boostmsg testunboost": {"desc": "Muestra cómo se vería el mensaje de unboost", "example": "boostmsg testunboost"},
    "boostmsg reward": {"desc": "Rol que recibe quien boostea el servidor", "syntax": "boostmsg reward (rol)", "example": "boostmsg reward @Booster"},
    "boostmsg removereward": {"desc": "Quita un rol de las recompensas de boost", "syntax": "boostmsg removereward (rol)", "example": "boostmsg removereward @Booster"},
    "boostmsg variables": {"desc": "Muestra las variables y etiquetas disponibles", "example": "boostmsg variables"},
    "boostmsg templates": {"desc": "Muestra plantillas listas para copiar", "example": "boostmsg templates"},
    "boostmsg reset": {"desc": "Borra la configuración de boost", "example": "boostmsg reset"},
    "embed": {"desc": "Guarda embeds por nombre para usarlos con {embed:nombre}", "syntax": "embed (subcomando)", "example": "embed create welcome_msg {embed}{description: hola {user.mention}}"},
    "embed create": {"desc": "Guarda un embed con nombre", "syntax": "embed create (nombre) (mensaje)", "example": "embed create welcome_msg {embed}{title: Bienvenido}{description: hola {user.mention}}"},
    "embed show": {"desc": "Muestra un embed guardado", "syntax": "embed show (nombre)", "example": "embed show welcome_msg"},
    "embed list": {"desc": "Lista los embeds guardados", "example": "embed list"},
    "embed delete": {"desc": "Borra un embed guardado", "syntax": "embed delete (nombre)", "example": "embed delete welcome_msg"},
    "afk": {"desc": "Te pone AFK con un estado", "syntax": "afk <estado>", "example": "afk comiendo, vuelvo en un rato"},
    "afklist": {"desc": "Muestra los miembros AFK del servidor", "example": "afklist"},
    "emojiinfo": {"desc": "Muestra información de un emoji personalizado", "syntax": "emojiinfo (emoji)", "example": "emojiinfo :pepe:"},
    "stickerinfo": {"desc": "Muestra información de un sticker (envíalo con el comando o responde a uno)", "example": "stickerinfo"},
    "stats": {"desc": "Muestra las estadísticas del bot", "example": "stats"},
}

# Nombres de parámetros (en inglés en el código) -> como se muestran en la sintaxis
PARAM_ES = {
    "member": "miembro", "user": "usuario", "reason": "razón", "channel": "canal",
    "amount": "cantidad", "seconds": "segundos", "duration": "duración", "role": "rol",
    "name": "nombre", "text": "texto", "n": "n", "url": "url", "code": "código",
    "message": "mensaje", "content": "contenido", "prize": "premio", "category": "categoría",
    "permissions": "permisos", "username": "usuario",
}


def required_permissions(command) -> list:
    """Permisos de Discord que pide un comando (incluye los de su grupo padre)."""
    perms = []
    for cmd in [command, *getattr(command, "parents", [])]:
        for chk in getattr(cmd, "checks", []):
            required = getattr(chk, "required_permissions", None)
            if required:
                perms.extend(p for p, v in required.items() if v and p not in perms)
    return perms


def build_command_card(ctx: commands.Context, command=None) -> discord.Embed:
    """Tarjeta de uso de un comando: 'Comando: x' + descripción + Sintaxis/Ejemplo."""
    command = command or ctx.command
    qualified = command.qualified_name
    info = COMMAND_INFO.get(qualified, {})

    prefix = DEFAULT_PREFIX
    if ctx.guild is not None:
        prefix = db.get_guild(ctx.guild.id).get("prefix", DEFAULT_PREFIX)

    if info.get("syntax"):
        syntax = prefix + info["syntax"]
    else:
        # obligatorios entre ( ), opcionales entre < >
        parts = []
        for pname, param in command.clean_params.items():
            label = PARAM_ES.get(pname, pname)
            parts.append(f"<{label}>" if not param.required else f"({label})")
        syntax = f"{prefix}{qualified} {' '.join(parts)}".strip()

    code_lines = [f"Sintaxis: {syntax}"]
    if info.get("example"):
        code_lines.append(f"Ejemplo: {prefix}{info['example']}")
    desc = info.get("desc") or command.short_doc or command.help or ""
    desc = desc.strip().split("\n")[0].rstrip(".")

    description = ""
    if desc:
        description += f"**{desc}**\n"
    description += "```\n" + "\n".join(code_lines) + "\n```"

    me = ctx.guild.me if ctx.guild is not None and ctx.guild.me is not None else ctx.bot.user
    e = discord.Embed(title=f"Comando: {qualified}", description=description, color=0x2b2d31)
    e.set_author(name=f"{me.display_name} help", icon_url=me.display_avatar.url)

    if isinstance(command, commands.Group) and command.commands:
        subs = ", ".join(f"`{c.name}`" for c in sorted(command.commands, key=lambda c: c.name))
        e.add_field(name="Subcomandos", value=subs, inline=False)

    perms = required_permissions(command)
    if perms:
        e.add_field(name="Permisos", value=", ".join(f"`{p}`" for p in perms), inline=False)
    return e
