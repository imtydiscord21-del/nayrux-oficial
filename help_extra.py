"""
help_extra.py — Categorías de ,help para los comandos nuevos (bienvenida, boost, embeds, AFK, info).
Se une a CATEGORIES en help.py con dos líneas (ver PARCHE_help.txt).
"""

EXTRA_CATEGORIES = {
    "bienvenidas": {
        "label": "Bienvenida y Boost",
        "description": "Mensajes de bienvenida y de boost con variables y embeds guardados.",
        "sections": [
            ("Bienvenida", [
                ",wlc config (canal) (mensaje)",
                ",wlc test",
                ",wlc variables",
                ",wlc templates",
                ",wlc reset",
            ], "Se envía cuando alguien entra al servidor. Usa `,wlc variables` para ver todo lo que puedes poner."),
            ("Boost", [
                ",boostmsg config (canal) (mensaje)",
                ",boostmsg unboostconfig (canal) (mensaje)",
                ",boostmsg test",
                ",boostmsg testunboost",
                ",boostmsg reward (rol)",
                ",boostmsg removereward (rol)",
                ",boostmsg variables",
                ",boostmsg templates",
                ",boostmsg reset",
            ], None),
            ("Embeds guardados", [
                ",embed create (nombre) (mensaje)",
                ",embed show (nombre)",
                ",embed list",
                ",embed delete (nombre)",
            ], "Se usan en los mensajes con `{embed:nombre}`."),
        ],
    },
    "extras": {
        "label": "AFK e Info extra",
        "description": "Estado AFK y datos de emojis, stickers y del bot.",
        "sections": [
            ("AFK", [
                ",afk [estado]",
                ",afklist",
            ], "Si alguien te menciona, el bot le avisa que estás AFK; al escribir, el estado se quita solo."),
            ("Información", [
                ",emojiinfo (emoji)",
                ",stickerinfo",
                ",stats",
            ], None),
        ],
    },
}
