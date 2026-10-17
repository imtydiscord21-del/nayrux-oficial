"""
msg_docs.py — Embeds de ayuda de ,wlc y ,boostmsg: variables, templates y uso de config.
Mismo diseño que las capturas (autor, título, descripción en cita, secciones, pie), en español.
"""

from aura_script import (
    USER_VARIABLES, GUILD_VARIABLES, GUILD_VARIABLES_BOOST,
    CHANNEL_VARIABLES, DATETIME_VARIABLES, BOOST_VARIABLES,
    FORMAT_TAGS, BUTTON_TAGS,
)
from aura_ui import info_embed, variable_lines

BOOST_EMOJI = "💎"


def variables_embed(ctx, kind: str):
    """kind: 'wlc' (bienvenida) o 'boost'."""
    if kind == "boost":
        title = f"{BOOST_EMOJI} Variables de Boost"
        desc = ["Variables disponibles para los mensajes de boost y unboost."]
        guild_vars = GUILD_VARIABLES_BOOST
        example = "{embed:boost}"
    else:
        title = "variables de bienvenida"
        desc = ["variables disponibles para los mensajes de bienvenida."]
        guild_vars = GUILD_VARIABLES
        example = "{embed:welcome}"

    custom = [
        "`{embed:nombre}` - usa un embed guardado",
        f"ejemplo: `{example}`",
        "créalo con `,embed create`",
    ]
    sections = [
        ("variables de usuario", variable_lines(USER_VARIABLES)),
        ("variables del servidor", variable_lines(guild_vars)),
        ("variables del canal", variable_lines(CHANNEL_VARIABLES)),
        ("fecha y hora", variable_lines(DATETIME_VARIABLES)),
        ("embeds personalizados", custom),
    ]
    if kind == "boost":
        sections.append(("variables de boost", variable_lines(BOOST_VARIABLES)))
        sections.append(("etiquetas de botón", [
            f"`{BUTTON_TAGS[0][0]}` - {BUTTON_TAGS[0][1]}",
            f"`{BUTTON_TAGS[1][0]}`",
            "el emoji es opcional",
        ]))
    else:
        custom.append("los botones se agregan con la etiqueta `{button: ...}`")
    sections.append(("etiquetas de formato (manual)", variable_lines(FORMAT_TAGS)))
    return info_embed(ctx, title, desc, sections)


def templates_embed(ctx, kind: str):
    if kind == "boost":
        cmd, title = ",boostmsg config", "plantillas de boost"
        what, saved = "boostear", "boost_msg"
        text = "gracias {user.mention} por boostear {guild.name}!"
        adv_desc = "gracias por boostear **{guild.name}**!"
        adv_footer = "ya tenemos {guild.boost_count} boosts!"
    else:
        cmd, title = ",wlc config", "plantillas de bienvenida"
        what, saved = "bienvenida", "welcome_msg"
        text = "bienvenido {user.mention} a {guild.name}!"
        adv_desc = "bienvenido a **{guild.name}**!"
        adv_footer = "ya somos {guild.count} miembros!"

    sections = [
        ("1 – embed personalizado", [
            f"primero crea: `,embed create {saved} (mensaje)`",
            "luego usa: " + f"`{cmd} #canal {{embed:{saved}}}`",
        ]),
        ("2 – texto simple (sin embed)", [f"`{cmd} #canal {text}`"]),
        ("3 – manual simple", [
            f"`{cmd} #canal {{content: {{user.mention}}}}{{embed}}"
            f"{{description: {text}}}{{thumbnail: {{user.avatar}}}}`"
        ]),
        ("4 – manual avanzado", [
            f"`{cmd} #canal {{content: {{user.mention}}}}{{embed}}"
            f"{{author: name: {{user.display}} && icon: {{user.avatar}}}}"
            f"{{description: {adv_desc}}}{{thumbnail: {{user.avatar}}}}"
            f"{{footer: text: {adv_footer}}}{{timestamp}}`"
        ]),
    ]
    desc = [
        f"plantillas prediseñadas para el mensaje de {what}.",
        "también puedes usar embeds personalizados con `{embed:nombre}`",
    ]
    return info_embed(ctx, title, desc, sections, footer=f"usa {cmd} para aplicar una plantilla")


def config_usage_embed(ctx, *, cmd: str, base: str, title: str, description: list, channel: str = "#bienvenida", sample: str = "bienvenido {user.mention} al servidor!"):
    """Uso de 'config' sin argumentos.  cmd = ',wlc config'   base = ',wlc'"""
    usage = [
        f"`{cmd} (canal) (mensaje)`",
        f"`{cmd} {channel} {{embed:welcome}}`",
        f"`{cmd} {channel} {{embed:welcome}} {sample}`",
        f"`{cmd} {channel} {sample}`",
    ]
    return info_embed(ctx, title, description, [
        ("uso", usage),
        ("variables", [f"usa `{base} variables` para ver todas las variables disponibles."]),
    ])
