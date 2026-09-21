import discord
from discord.ext import commands
from config import db
import logging

log = logging.getLogger("antinuke.help")

SUPPORT_SERVER_URL = "https://discord.gg/SQEATzU7HF"
BRAND_ICON_URL = "https://i.pinimg.com/736x/78/ab/07/78ab072e66ef17fe638524e9a072cc74.jpg"  # ya no se usa como thumbnail del help (ahora usa el ícono del server)

# ── Tabla de comandos ──────────────────────────────────────────────────────
# Cada categoría tiene "sections": lista de (subtítulo, [comandos], nota_opcional)

CATEGORIES = {
    "automation": {
        "label": "Automation",
        "description": "AutoRole, AutoReact y AutoGreet — automatiza roles, reacciones y bienvenidas.",
        "sections": [
            ("AutoRole", [
                ",autorole setup <rol>",
                ",autorole toggle",
                ",autorole add <rol>",
                ",autorole remove <rol>",
                ",autorole addbot <rol>",
                ",autorole removebot <rol>",
                ",autorole list",
                ",autorole clear",
                ",autorole info",
                ",autorole reset",
            ], None),
            ("AutoReact", [
                ",autoreact add <trigger> <emoji>",
                ",autoreact remove <trigger>",
                ",autoreact list",
                ",autoreact clear",
                ",autoreact test <trigger>",
            ], None),
            ("AutoGreet", [
                ",autogreet <#canal>",
                ",autogreet off",
                ",automsg <mensaje>",
            ], "Variables: `{user}` `{username}` `{server}` `{membercount}`"),
        ],
    },
    "integrations": {
        "label": "Integrations",
        "description": "Integración y búsquedas de Roblox.",
        "sections": [
            ("Roblox", [
                ",roblox",
                ",rblx",
                ",roblox user",
                ",roblox value",
                ",roblox presence",
                ",roblox avatar",
                ",roblox wearing",
                ",roblox friends",
                ",roblox inventory",
                ",roblox group",
                ",roblox groups",
                ",roblox game",
            ], "`,roblox value` usa un servicio no oficial (Rolimons) y puede fallar sin aviso."),
        ],
    },
    "security": {
        "label": "Security",
        "description": "Protegé tu servidor de raids, nukes, spam y links maliciosos.",
        "sections": [
            ("Anti Modules", [
                ",antinuke",
                ",antiraid",
                ",antispam",
                ",antilink",
                ",antiinvite",
                ",antibot",
                ",antiwebhook",
                ",antimention",
                ",antitoken",
                ",whitelist",
            ], "Cada comando abre el panel de configuración de ese módulo: activar/desactivar, castigo, canal de logs, threshold y whitelist propios."),
            ("Configuración Avanzada", [
                ",antinuke enable / disable",
                ",antinuke status",
                ",antinuke modules",
                ",antinuke punishment <ban|kick|strip|mute>",
                ",antinuke threshold <módulo> <n>",
                ",antinuke window <módulo> <segundos>",
                ",antinuke accountage <días>",
                ",antinuke guildage <días>",
                ",antinuke reset",
            ], None),
        ],
    },
    "moderacion": {
        "label": "Moderación",
        "description": "Kicks, baneos, silencios, advertencias, purgas, cuarentena y bloqueo del servidor.",
        "sections": [
            ("Moderación", [
                ",kick <usuario> [razón]",
                ",ban <usuario> [días_borrado] [razón]",
                ",softban <usuario> [razón]",
                ",mute <usuario> <duración> [razón]",
                ",unmute <usuario> [razón]",
                ",warn <usuario> [razón]",
                ",warnings <usuario>",
                ",clearwarns <usuario>",
                ",delwarn <usuario> <índice>",
                ",purge <cantidad> [usuario]",
                ",lockchannel [#canal]",
                ",unlockchannel [#canal]",
                ",slowmode <segundos> [#canal]",
                ",nick <usuario> <apodo|reset>",
                ",role add <usuario> <rol>",
                ",role remove <usuario> <rol>",
                ",modlogs <usuario>",
            ], None),
            ("Jail", [
                ",setupjail",
                ",jail <usuario> [razón]",
                ",unjail <usuario> [razón]",
            ], None),
            ("Lockdown", [
                ",lockdown",
                ",unlock",
                ",lockdown exempt add <canal>",
                ",lockdown exempt remove <canal>",
                ",lockdown exempt list",
            ], None),
            ("Desbaneos", [
                ",unban <id_usuario> [razón]",
                ",unbanall",
            ], None),
        ],
    },
    "configuracion": {
        "label": "Configuración",
        "description": "Prefijo, canal de logs, apariencia de embeds y configuración rápida del bot.",
        "sections": [
            ("Ajustes", [
                ",setlogs [#canal]",
                ",setprefix <prefijo>",
                ",logembed color <hex>",
                ",logembed footer <texto>",
                ",logembed thumbnail <on|off>",
            ], None),
            ("Auto-Configuración", [
                ",setuplogs",
                ",autosetup normal",
                ",autosetup rapido",
            ], None),
        ],
    },
    "whitelist": {
        "label": "Whitelist",
        "description": "Usuarios completamente exentos de la detección AntiNuke.",
        "sections": [
            ("Whitelist", [
                ",whitelist",
                ",whitelist add <usuario>",
                ",whitelist remove <usuario>",
                ",whitelist clear",
                ",whitelist check <usuario>",
            ], None),
        ],
    },
    "voz": {
        "label": "Voz",
        "description": "Rastreo de actividad en canales de voz y canales temporales tipo Join-to-Create.",
        "sections": [
            ("VC Tracker", [
                ",setvc channel <#canal>",
                ",setvc threshold <n>",
                ",vcstats",
            ], None),
            ("VoiceMaster", [
                ",voicemaster",
                ",vm",
                ",voicemaster setup",
                ",voicemaster reset",
                ",voicemaster panel",
            ], "Lock/Unlock · Hide/Reveal · Rename · Limit · Kick · Claim"),
        ],
    },
    "bienvenidas": {
        "label": "Bienvenidas",
        "description": "Mensajes de bienvenida personalizados, con embeds, botones y variables.",
        "sections": [
            ("Bienvenidas", [
                ",welcome add <#canal> <config>",
                ",welcome list",
                ",welcome remove <n>",
                ",welcome test",
                ",welcome off",
            ], None),
        ],
    },
    "invitaciones": {
        "label": "Invitaciones",
        "description": "Rastrea cuántas invitaciones trae cada miembro y recompensa a los que más invitan.",
        "sections": [
            ("Invitaciones", [
                ",setinvite channel <#canal>",
                ",setinvite threshold <n> [recompensa]",
                ",setinvite altdays <días>",
                ",invites [usuario]",
                ",invitetop",
                ",resetinvites",
            ], None),
        ],
    },
    "giveaways": {
        "label": "Giveaways",
        "description": "Sorteos con botón de participación, bonus de probabilidad y reroll.",
        "sections": [
            ("Giveaways", [
                ",gcreate <#canal> <duración> <premio>",
                ",gend <id_mensaje>",
                ",greroll <id_mensaje>",
                ",gbonus <usuario> <porcentaje>",
                ",gbonus remove <usuario>",
                ",gbonus list",
            ], None),
        ],
    },
    "imagenes": {
        "label": "Reenvío de Imágenes",
        "description": "Manda links de fotos/gifs por DM al bot y elige con botones a cuál canal reenviarlos.",
        "sections": [
            ("Canales y Acceso", [
                ",addpostchannel <nombre> <#canal>",
                ",removepostchannel <nombre>",
                ",postchannels",
                ",posters add <usuario>",
                ",posters remove <usuario>",
                ",posters",
            ], None),
            ("Uso", [
                ",post <link1> <link2> ...",
                ",preview",
            ], None),
        ],
    },
    "autoresponder": {
        "label": "Autoresponders",
        "description": "Respuestas automáticas a palabras o frases exactas, en texto o embed.",
        "sections": [
            ("Autoresponders", [
                ",autoresponder add <trigger> | <respuesta>",
                ",autoresponder remove <trigger>",
                ",autoresponder list",
                ",autoresponder clear",
            ], None),
        ],
    },
    "embeds": {
        "label": "Embeds Personalizados",
        "description": "Crea y edita embeds con un motor de sintaxis simple, compatible con las bienvenidas.",
        "sections": [
            ("Embeds", [
                ",createembed <código>",
                ",editembed <link_mensaje> <código>",
            ], "Sintaxis: `{embed}$v{title: ...}$v{description: ...}$v{color: #hex}$v{field: nombre && valor && inline}`\nVariables: `{user.mention}` `{user.tag}` `{guild.name}` `{guild.count}` `{channel.mention}`"),
        ],
    },
    "information": {
        "label": "Information",
        "description": "Ver información detallada de servidor, usuarios, roles y canales.",
        "sections": [
            ("Server", [
                ",serverinfo",
                ",servericon",
                ",serverbanner",
                ",membercount",
                ",boosts",
                ",boosters",
                ",owner",
                ",roles",
            ], None),
            ("User", [
                ",userinfo",
                ",avatar",
                ",banner",
                ",spotify",
                ",voiceinfo",
                ",displayname",
            ], None),
            ("Channel & Role", [
                ",channelinfo",
                ",roleinfo",
            ], None),
            ("Bot", [
                ",ping",
                ",uptime",
                ",botinfo",
                ",inviteinfo",
            ], None),
            ("Utility", [
                ",snowflake",
                ",id",
                ",colorinfo",
                ",position",
                ",created",
                ",joined",
            ], None),
            ("Messages", [
                ",firstmessage",
                ",lastmessage",
                ",messageinfo",
                ",snipe / ,s",
                ",editsnipe / ,es",
            ], None),
            ("Lookup", [
                ",vanityinfo",
                ",permissions",
                ",auditlogs",
                ",list",
            ], None),
        ],
    },
    "emoji": {
        "label": "Emoji Commands",
        "description": "Administrá y organizá los emojis del servidor.",
        "sections": [
            ("Info & Search", [
                ",emoji <emoji>",
                ",emojilist",
                ",emojisearch <texto>",
                ",emojistats",
                ",bigemoji <emoji>",
            ], None),
            ("Management", [
                ",steal <emoji>",
                ",emojiadd <nombre> <url>",
                ",deleteemoji <emoji>",
                ",renameemoji <emoji> <nombre>",
                ",copyemojis <emoji1> <emoji2> ...",
            ], None),
            ("Role Icon", [
                ",roleicon <rol> <emoji|url>",
                ",roleicon set <rol> <emoji|url>",
                ",roleicon remove <rol>",
                ",roleicon info <rol>",
            ], "Necesita que el servidor tenga el boost/nivel suficiente para íconos de rol."),
        ],
    },
    "backup": {
        "label": "Respaldo",
        "description": "Copias de seguridad del servidor para restaurar canales y roles tras un ataque.",
        "sections": [
            ("Respaldo", [
                ",backup snapshot",
                ",backup restore",
                ",backup status",
            ], None),
        ],
    },
    "premium": {
        "label": "Premium",
        "description": "Exclusivo para el dueño del bot y el dueño del servidor.",
        "sections": [
            ("Perfil del Bot", [
                ",changeavatar <url>",
                ",changebanner <url>",
                ",changename <nombre>",
                ",resetprofile",
            ], None),
            ("Perfil del Servidor", [
                ",guildicon <url>",
                ",guildbanner <url>",
            ], None),
            ("Utilidad", [
                ",selfpurge [cantidad]",
            ], None),
        ],
    },
}

ALIASES = {
    "utilities": "information", "utils": "information", "utilidades": "information", "info": "information",
    "roblox": "integrations", "rblx": "integrations", "integrations": "integrations", "integraciones": "integrations",
    "autorole": "automation", "autoreact": "automation", "autogreet": "automation",
    "automation": "automation", "automatizacion": "automation", "automatización": "automation",
    "mod": "moderacion", "moderation": "moderacion", "moderación": "moderacion",
    "jail": "moderacion", "lockdown": "moderacion", "unban": "moderacion",
    "antinuke": "security", "modules": "security", "módulos": "security", "modulos": "security",
    "emojis": "emoji",
    "images": "imagenes", "imagedrop": "imagenes", "fotos": "imagenes",
    "log": "configuracion", "logs": "configuracion", "settings": "configuracion",
    "setup": "configuracion", "auto": "configuracion", "autoconfig": "configuracion", "autosetup": "configuracion",
    "vctracker": "voz", "voicechannel": "voz", "voice": "voz", "voicemaster": "voz", "vm": "voz",
    "welcome": "bienvenidas",
    "invites": "invitaciones", "invite": "invitaciones",
    "giveaway": "giveaways", "sorteos": "giveaways", "sorteo": "giveaways",
    "respaldo": "backup",
}


def _localize(cmd: str, prefix: str) -> str:
    """Reemplaza la ',' con la que están escritos los comandos de CATEGORIES
    por el prefix real configurado en el server."""
    return prefix + cmd[1:] if cmd.startswith(",") else cmd


def _guild_icon(guild: discord.Guild) -> str | None:
    return guild.icon.url if guild and guild.icon else None


def _total_commands() -> int:
    return sum(len(cmds) for data in CATEGORIES.values() for _, cmds, _ in data["sections"])


def _bot_invite_url(bot: discord.Client) -> str:
    return discord.utils.oauth_url(bot.user.id, permissions=discord.Permissions(administrator=True))


def _build_overview_embed(bot: discord.Client, guild: discord.Guild, prefix: str) -> discord.Embed:
    e = discord.Embed(
        description=(
            f"**Prefix:** `{prefix}`\n"
            f"**Commands:** `{_total_commands()}` | **Categories:** `{len(CATEGORIES)}`\n\n"
            f"[Support Server]({SUPPORT_SERVER_URL}) | [Bot Invite]({_bot_invite_url(bot)})\n\n"
            "Selecciona una categoría abajo para ver sus comandos."
        ),
        color=0x2b2d31,
    )
    e.set_author(name=f"{bot.user.name} Help", icon_url=bot.user.display_avatar.url)
    icon = _guild_icon(guild)
    if icon:
        e.set_thumbnail(url=icon)
    e.set_footer(text=f"Usa {prefix}help <comando> para ayuda de un comando específico")
    return e


def _build_category_embed(bot: discord.Client, guild: discord.Guild, cat_key: str, prefix: str) -> discord.Embed:
    data = CATEGORIES[cat_key]
    e = discord.Embed(title=data["label"], color=0x2b2d31)
    e.set_author(name=f"{bot.user.name} Help", icon_url=bot.user.display_avatar.url)
    icon = _guild_icon(guild)
    if icon:
        e.set_thumbnail(url=icon)

    parts = [f"**Prefix:** `{prefix}`\n{data['description']}"]
    for subheader, cmds, note in data["sections"]:
        localized = [_localize(c, prefix) for c in cmds]
        block = "```\n" + "\n".join(localized) + "\n```"
        parts.append(f"**{subheader}**\n{block}")
        if note:
            parts.append(note)
    e.description = "\n".join(parts)

    e.set_footer(text=f"Selecciona una categoría desde el menú de abajo · {bot.user.name}")
    e.timestamp = discord.utils.utcnow()
    return e


HELP_TTL_SECONDS = 120


CATEGORY_EMOJIS = {
    "automation": "🤖",
    "integrations": "🔗",
    "security": "🔒",
    "moderacion": "🛡️",
    "configuracion": "⚙️",
    "whitelist": "✅",
    "voz": "🔊",
    "bienvenidas": "👋",
    "invitaciones": "📩",
    "giveaways": "🎁",
    "imagenes": "🖼️",
    "autoresponder": "💬",
    "embeds": "📝",
    "information": "ℹ️",
    "emoji": "😀",
    "backup": "💾",
    "premium": "⭐",
}


class CategorySelect(discord.ui.Select):
    def __init__(self, bot: discord.Client, guild: discord.Guild, prefix: str, view: "HelpView"):
        self.bot = bot
        self.guild = guild
        self.prefix = prefix
        self.outer_view = view
        options = [
            discord.SelectOption(label="Inicio", value="__home__", description="Volver al menú principal", emoji="🏠"),
        ] + [
            discord.SelectOption(
                label=data["label"], value=key, description=data["description"][:100],
                emoji=CATEGORY_EMOJIS.get(key),
            )
            for key, data in CATEGORIES.items()
        ]
        super().__init__(placeholder="Selecciona una categoría...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.outer_view.is_expired():
            return await interaction.response.send_message(
                embed=discord.Embed(description=f"Help menu expired. Run `{self.prefix}help` again.", color=0x2b2d31),
                ephemeral=True,
            )
        if self.values[0] == "__home__":
            embed = _build_overview_embed(self.bot, self.guild, self.prefix)
        else:
            embed = _build_category_embed(self.bot, self.guild, self.values[0], self.prefix)
        await interaction.response.edit_message(embed=embed, view=self.outer_view)


class HelpView(discord.ui.View):
    def __init__(self, bot: discord.Client, guild: discord.Guild, prefix: str):
        super().__init__(timeout=None)  # el "timeout" real lo maneja is_expired(), no discord.py
        self.bot = bot
        self.prefix = prefix
        self.created_at = discord.utils.utcnow()
        self.message: discord.Message | None = None
        self.add_item(CategorySelect(bot, guild, prefix, self))
        self.add_item(discord.ui.Button(label="Support Server", url=SUPPORT_SERVER_URL, style=discord.ButtonStyle.link))
        self.add_item(discord.ui.Button(label="Bot Invite", url=_bot_invite_url(bot), style=discord.ButtonStyle.link))

    def is_expired(self) -> bool:
        return (discord.utils.utcnow() - self.created_at).total_seconds() > HELP_TTL_SECONDS



class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx, *, category: str = None):
        """Muestra la ayuda general o de una categoría específica."""
        config = db.get_guild(ctx.guild.id)
        prefix = config.get("prefix", ",")

        if category is None:
            embed = _build_overview_embed(self.bot, ctx.guild, prefix)
            view = HelpView(self.bot, ctx.guild, prefix)
            view.message = await ctx.send(embed=embed, view=view)
            return

        cat_key = category.lower().strip()
        cat_key = ALIASES.get(cat_key, cat_key)

        if cat_key not in CATEGORIES:
            available = " · ".join(f"`{k}`" for k in CATEGORIES)
            e = discord.Embed(
                description=f"Categoría `{category}` no encontrada.\nDisponibles: {available}",
                color=0x2b2d31,
            )
            e.set_author(name=f"{self.bot.user.name} Help", icon_url=self.bot.user.display_avatar.url)
            return await ctx.send(embed=e)

        embed = _build_category_embed(self.bot, ctx.guild, cat_key, prefix)
        view = HelpView(self.bot, ctx.guild, prefix)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
