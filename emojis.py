"""
emojis.py — Constantes de los emojis personalizados de la app (Developer Portal
→ Emojis). Completá los 4 IDs de abajo una vez que los subas ahí; el nombre
tiene que coincidir EXACTO con el que le pusiste en el portal.

Cómo usarlos en el código: from emojis import ADD, REMOVE, DENY, CHECK
    await ctx.send(f"{CHECK} Listo.")
"""

# Reemplazá cada 0 por el ID real del emoji subido al Developer Portal.
ADD = "<:add_blue:1551303940786626640>"        # cruz azul (+)
REMOVE = "<:remove_red:1551303956825772114>"   # X roja
DENY = "<:minus_blue:1551303971216556032>"     # línea azul (–) — "no permitido / desactivado"
CHECK = "<:check_green:1551303984495468656>"   # tilde verde

# ── VoiceMaster ──────────────────────────────────────────────────────────────
VM_LOCK = "<:lock:1551304227635204126>"
VM_UNLOCK = "<:unlock:1551304354391269456>"
VM_VER = "<:ver:1551304364025712640>"          # revelar canal
VM_NOVER = "<:nover:1551304325681254480>"      # ocultar canal
VM_PANTALLA = "<:pantalla:1551304342496088064>"
VM_NOTAS = "<:notas:1551304312708407418>"
VM_MICROFONO = "<:microfono:1551304296266600580>"
VM_MENOS = "<:menos:1551304286481289346>"
VM_MAS = "<:mas:1551304273755639911>"
VM_MARTILLO = "<:martillo:1551304262934601951>"
VM_LOGO = "<:logo:1551304248803856504>"
