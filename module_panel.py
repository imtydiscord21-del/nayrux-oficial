"""
module_panel.py — Panel interactivo de configuración por módulo.

Cada módulo de AntiNuke puede tener su propio castigo, canal de logs y
whitelist (usuarios + roles), independientes de la configuración global.
Si un módulo no tiene nada propio configurado, todo cae de vuelta a la
configuración global (compatibilidad con servidores existentes).
"""

import discord
from config import db
from settings import MODULES

MODULE_LABELS = {
    "ban": "Anti-Ban Masivo",
    "kick": "Anti-Kick Masivo",
    "channeldelete": "Anti-Eliminación de Canales",
    "channelcreate": "Anti-Creación de Canales",
    "roledelete": "Anti-Eliminación de Roles",
    "rolecreate": "Anti-Creación de Roles",
    "roleadd": "Anti-Asignación de Roles",
    "webhook": "Anti-Webhook",
    "mention": "Anti-Spam de Menciones",
    "emojidelete": "Anti-Eliminación de Emojis",
    "botadd": "Anti-Bot Add",
    "everyone": "Anti-Mención Everyone",
    "serverupdate": "Anti-Actualización del Servidor",
    "prune": "Anti-Prune",
    "roleperm": "Anti-Permisos de Rol",
    "raid": "Anti-Raid (oleada de joins)",
    "spam": "Anti-Spam de Mensajes",
    "link": "Anti-Link",
    "invite": "Anti-Invite",
    "token": "Anti-Token Filtrado",
}

PUNISHMENT_CHOICES = ("ban", "kick", "strip", "mute")


def _invalidate_cache(guild_id: int):
    try:
        from antinuke import invalidate_config_cache
        invalidate_config_cache(guild_id)
    except ImportError:
        pass


def _get_module_config(config: dict, module_key: str) -> dict:
    return config.get("module_settings", {}).get(module_key, {})


def _save_module_config(guild_id: int, module_key: str, **updates):
    for key, value in updates.items():
        db.set_guild_field(guild_id, f"module_settings.{module_key}.{key}", value)
    _invalidate_cache(guild_id)


async def _require_manager(interaction: discord.Interaction, bot: discord.Client) -> bool:
    guild, user = interaction.guild, interaction.user
    if guild is None or not isinstance(user, discord.Member):
        allowed = False
    elif user.id == guild.owner_id or user.guild_permissions.administrator:
        allowed = True
    else:
        allowed = await bot.is_owner(user)
        if not allowed:
            allowed = user.id in db.get_guild(guild.id).get("antinuke_admins", [])
    if not allowed:
        await interaction.response.send_message(
            "Solo el dueño, un administrador o un AntiNuke Admin puede cambiar esta configuración.",
            ephemeral=True,
        )
    return allowed


# ── Embeds ──────────────────────────────────────────────────────────────────

def build_module_embed(bot: discord.Client, guild: discord.Guild, module_key: str) -> discord.Embed:
    config = db.get_guild(guild.id)
    an = config.get("antinuke", {})
    toggle_key, threshold_key, window_key = MODULES[module_key]
    mod_cfg = _get_module_config(config, module_key)

    enabled = an.get("enabled", False) and an.get(toggle_key, True)
    punishment = mod_cfg.get("punishment") or an.get("punishment", "ban")
    is_override = bool(mod_cfg.get("punishment"))
    log_channel_id = mod_cfg.get("log_channel")
    log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
    log_text = f"<#{log_channel.id}>" if log_channel else "Usa el canal global"
    wl = mod_cfg.get("whitelist", {})
    wl_count = len(wl.get("users", [])) + len(wl.get("roles", []))

    lines = [
        f"**Estado efectivo:** {'Activado' if enabled else 'Desactivado'}",
        f"**Castigo:** `{punishment}`" + (" *(propio)*" if is_override else " *(global)*"),
        f"**Canal de registros:** {log_text}",
        f"**Excepciones:** {wl_count} usuarios o roles",
    ]
    if threshold_key:
        lines.append(f"**Límite:** {an.get(threshold_key, 3)} acciones en {an.get(window_key, 10)} s")

    e = discord.Embed(title=MODULE_LABELS.get(module_key, module_key), description="\n".join(lines), color=0x2b2d31)
    e.set_author(name=f"{bot.user.name}", icon_url=bot.user.display_avatar.url)
    e.set_footer(text="Los ajustes propios de este módulo tienen prioridad sobre los globales.")
    return e


def build_whitelist_embed(module_key: str, guild: discord.Guild) -> discord.Embed:
    config = db.get_guild(guild.id)
    wl = _get_module_config(config, module_key).get("whitelist", {})
    users = wl.get("users", [])
    roles = wl.get("roles", [])

    user_text = "\n".join(f"<@{u}>" for u in users) or "Ninguno"
    role_text = "\n".join(f"<@&{r}>" for r in roles) or "Ninguno"

    e = discord.Embed(
        title="Excepciones del módulo",
        description=f"Usuarios y roles que quedan fuera de **{MODULE_LABELS.get(module_key, module_key)}**.",
        color=0x2b2d31,
    )
    e.add_field(name=f"Usuarios ({len(users)})", value=user_text[:1024], inline=False)
    e.add_field(name=f"Roles ({len(roles)})", value=role_text[:1024], inline=False)
    e.set_footer(text="Estas excepciones solo aplican a este módulo.")
    return e


# ── Modales ─────────────────────────────────────────────────────────────────

class PunishmentModal(discord.ui.Modal, title="Configurar castigo"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.value_input = discord.ui.TextInput(
            label="Castigo del módulo",
            placeholder="ban, kick, strip, mute o global",
            required=True,
            max_length=10,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        value = self.value_input.value.strip().lower()
        if value == "global":
            _save_module_config(interaction.guild.id, self.module_key, punishment=None)
            embed = build_module_embed(self.bot, interaction.guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.parent_view)
        if value not in PUNISHMENT_CHOICES:
            return await interaction.response.send_message(
                f"Castigo inválido. Usa uno de: {', '.join(PUNISHMENT_CHOICES)} o `global`.", ephemeral=True
            )
        _save_module_config(interaction.guild.id, self.module_key, punishment=value)
        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class LogsModal(discord.ui.Modal, title="Configurar canal de registros"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.value_input = discord.ui.TextInput(
            label="Canal o mención del canal",
            placeholder="#logs o el ID del canal (vacío = usar el canal global)",
            required=False,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        raw = self.value_input.value.strip()
        if not raw:
            _save_module_config(interaction.guild.id, self.module_key, log_channel=None)
            embed = build_module_embed(self.bot, interaction.guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.parent_view)

        channel_id = "".join(ch for ch in raw if ch.isdigit())
        if not channel_id:
            return await interaction.response.send_message(
                "Canal inválido. Usa un #mention o el ID del canal.", ephemeral=True
            )
        channel = interaction.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("No encontré ese canal de texto en este servidor.", ephemeral=True)

        _save_module_config(interaction.guild.id, self.module_key, log_channel=channel.id)
        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class ThresholdModal(discord.ui.Modal, title="Configurar límite"):
    def __init__(self, bot: discord.Client, module_key: str, parent_view: discord.ui.View):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.parent_view = parent_view
        self.threshold_input = discord.ui.TextInput(label="Acciones antes de activar", placeholder="ej. 3 (máximo 1000)", required=True, max_length=4)
        self.window_input = discord.ui.TextInput(label="Ventana de tiempo en segundos", placeholder="ej. 10 (máximo 3600)", required=True, max_length=4)
        self.add_item(self.threshold_input)
        self.add_item(self.window_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        t_raw = self.threshold_input.value.strip()
        w_raw = self.window_input.value.strip()
        if not (t_raw.isdigit() and w_raw.isdigit()):
            return await interaction.response.send_message("El límite y la ventana deben ser números.", ephemeral=True)

        threshold, window = int(t_raw), int(w_raw)
        if not 1 <= threshold <= 1000 or not 1 <= window <= 3600:
            return await interaction.response.send_message(
                "Usa entre 1 y 1000 acciones, y entre 1 y 3600 segundos.", ephemeral=True
            )

        toggle_key, threshold_key, window_key = MODULES[self.module_key]
        db.set_guild_field(interaction.guild.id, f"antinuke.{threshold_key}", threshold)
        db.set_guild_field(interaction.guild.id, f"antinuke.{window_key}", window)
        _invalidate_cache(interaction.guild.id)

        embed = build_module_embed(self.bot, interaction.guild, self.module_key)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class WhitelistAddModal(discord.ui.Modal, title="Agregar excepción"):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.value_input = discord.ui.TextInput(
            label="Usuario o Rol (mención o ID)",
            placeholder="@usuario, @rol, o su ID",
            required=True,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        raw_id = "".join(ch for ch in self.value_input.value.strip() if ch.isdigit())
        if not raw_id:
            return await interaction.response.send_message("No pude leer un ID válido ahí.", ephemeral=True)
        entry_id = int(raw_id)

        guild = interaction.guild
        role = guild.get_role(entry_id)
        member = guild.get_member(entry_id)
        if role is None and member is None:
            try:
                member = await guild.fetch_member(entry_id)
            except (discord.NotFound, discord.HTTPException):
                member = None

        if member is not None:
            db.add_guild_set_item(
                guild.id, f"module_settings.{self.module_key}.whitelist.users", entry_id
            )
        elif role is not None:
            db.add_guild_set_item(
                guild.id, f"module_settings.{self.module_key}.whitelist.roles", entry_id
            )
        else:
            return await interaction.response.send_message(
                "No encontré ese usuario ni ese rol en este servidor.", ephemeral=True
            )

        _invalidate_cache(guild.id)

        embed = build_whitelist_embed(self.module_key, guild)
        await interaction.response.edit_message(embed=embed, view=WhitelistView(self.bot, self.module_key))


class WhitelistRemoveModal(discord.ui.Modal, title="Quitar excepción"):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__()
        self.bot = bot
        self.module_key = module_key
        self.value_input = discord.ui.TextInput(
            label="Usuario o Rol (mención o ID)",
            placeholder="@usuario, @rol, o su ID",
            required=True,
            max_length=100,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        raw_id = "".join(ch for ch in self.value_input.value.strip() if ch.isdigit())
        if not raw_id:
            return await interaction.response.send_message("No pude leer un ID válido ahí.", ephemeral=True)
        entry_id = int(raw_id)

        guild = interaction.guild
        removed_user = db.remove_guild_set_item(
            guild.id, f"module_settings.{self.module_key}.whitelist.users", entry_id
        )
        removed_role = db.remove_guild_set_item(
            guild.id, f"module_settings.{self.module_key}.whitelist.roles", entry_id
        )

        if not (removed_user or removed_role):
            return await interaction.response.send_message("Esa entrada no estaba en la whitelist.", ephemeral=True)

        _invalidate_cache(guild.id)

        embed = build_whitelist_embed(self.module_key, guild)
        await interaction.response.edit_message(embed=embed, view=WhitelistView(self.bot, self.module_key))


# ── Vistas ──────────────────────────────────────────────────────────────────

class WhitelistView(discord.ui.View):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__(timeout=120)
        self.bot = bot
        self.module_key = module_key

    @discord.ui.button(label="Agregar excepción", style=discord.ButtonStyle.success)
    async def add_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_manager(interaction, self.bot):
            return
        await interaction.response.send_modal(WhitelistAddModal(self.bot, self.module_key))

    @discord.ui.button(label="Quitar excepción", style=discord.ButtonStyle.danger)
    async def remove_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_manager(interaction, self.bot):
            return
        await interaction.response.send_modal(WhitelistRemoveModal(self.bot, self.module_key))

    @discord.ui.button(label="Actualizar", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_manager(interaction, self.bot):
            return
        embed = build_whitelist_embed(self.module_key, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_manager(interaction, self.bot):
            return
        await interaction.response.edit_message(content="Panel cerrado.", embed=None, view=None)


class ModuleActionSelect(discord.ui.Select):
    def __init__(self, bot: discord.Client, module_key: str):
        self.bot = bot
        self.module_key = module_key
        toggle_key, threshold_key, window_key = MODULES[module_key]

        options = [
            discord.SelectOption(label="Activar", value="enable", description=f"Activar {MODULE_LABELS.get(module_key, module_key)}"),
            discord.SelectOption(label="Desactivar", value="disable", description=f"Desactivar {MODULE_LABELS.get(module_key, module_key)}"),
            discord.SelectOption(label="Castigo", value="punishment", description="Elegir un castigo propio o heredar el global"),
            discord.SelectOption(label="Canal de registros", value="logs", description="Elegir un canal propio o usar el global"),
        ]
        if threshold_key:
            options.append(discord.SelectOption(label="Límite y ventana", value="threshold", description="Configurar cuántas acciones y en cuánto tiempo"))
        options.append(discord.SelectOption(label="Excepciones", value="whitelist", description="Agregar usuarios o roles exentos"))
        options.append(discord.SelectOption(label="Restablecer módulo", value="reset", description="Quitar ajustes propios y heredar los globales"))

        super().__init__(placeholder="Elige qué quieres personalizar…", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        action = self.values[0]
        guild = interaction.guild
        toggle_key, threshold_key, window_key = MODULES[self.module_key]

        if action in ("enable", "disable"):
            db.set_guild_field(guild.id, f"antinuke.{toggle_key}", action == "enable")
            _invalidate_cache(guild.id)
            embed = build_module_embed(self.bot, guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.view)

        if action == "reset":
            db.set_guild_field(guild.id, f"module_settings.{self.module_key}", {})
            _invalidate_cache(guild.id)
            embed = build_module_embed(self.bot, guild, self.module_key)
            return await interaction.response.edit_message(embed=embed, view=self.view)

        if action == "punishment":
            return await interaction.response.send_modal(PunishmentModal(self.bot, self.module_key, self.view))

        if action == "logs":
            return await interaction.response.send_modal(LogsModal(self.bot, self.module_key, self.view))

        if action == "threshold":
            return await interaction.response.send_modal(ThresholdModal(self.bot, self.module_key, self.view))

        if action == "whitelist":
            embed = build_whitelist_embed(self.module_key, guild)
            view = WhitelistView(self.bot, self.module_key)
            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ModuleConfigView(discord.ui.View):
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__(timeout=180)
        self.add_item(ModuleActionSelect(bot, module_key))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class BackToModulesButton(discord.ui.Button):
    def __init__(self, bot: discord.Client):
        super().__init__(label="◀ Módulos", style=discord.ButtonStyle.secondary, row=1)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        embed = build_modules_browser_embed(interaction.guild)
        view = ModuleBrowserView(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class ModuleConfigWithBackView(discord.ui.View):
    """Igual que ModuleConfigView, pero con un botón para volver al browser de módulos."""
    def __init__(self, bot: discord.Client, module_key: str):
        super().__init__(timeout=180)
        self.add_item(ModuleActionSelect(bot, module_key))
        self.add_item(BackToModulesButton(bot))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


def build_modules_browser_embed(guild: discord.Guild) -> discord.Embed:
    e = discord.Embed(
        title="Módulos de AntiNuke",
        description=(
            f"Este servidor tiene **{len(MODULES)}** módulos de protección.\n"
            "Elige uno para activar o desactivar la protección, ajustar el castigo, "
            "elegir el canal de registros, gestionar excepciones o cambiar su límite."
        ),
        color=0x2b2d31,
    )
    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)
    return e


class ModuleBrowserSelect(discord.ui.Select):
    def __init__(self, bot: discord.Client):
        self.bot = bot
        options = [
            discord.SelectOption(label=MODULE_LABELS.get(key, key), value=key)
            for key in MODULES
        ]
        super().__init__(placeholder="Selecciona un módulo para configurar...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not await _require_manager(interaction, self.bot):
            return
        module_key = self.values[0]
        embed = build_module_embed(self.bot, interaction.guild, module_key)
        view = ModuleConfigWithBackView(self.bot, module_key)
        await interaction.response.edit_message(embed=embed, view=view)


class ModuleBrowserView(discord.ui.View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=180)
        self.add_item(ModuleBrowserSelect(bot))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
