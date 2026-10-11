import discord
from discord.ext import commands, tasks
import asyncio
import os
import logging
from config import db, DEFAULT_PREFIX
from webhook_utils import send_via_webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("antinuke")

# Tarjeta de ayuda "falta un argumento" (estilo bender, en español).
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
}

# Nombres de parámetros (en inglés en el código) -> como se muestran en la sintaxis
PARAM_ES = {
    "member": "miembro", "user": "usuario", "reason": "razón", "channel": "canal",
    "amount": "cantidad", "seconds": "segundos", "duration": "duración", "role": "rol",
    "name": "nombre", "text": "texto", "n": "n", "url": "url", "code": "código",
    "message": "mensaje", "content": "contenido", "prize": "premio", "category": "categoría",
}


def build_command_card(ctx: commands.Context) -> discord.Embed:
    """Tarjeta de uso de un comando: 'Comando: x' + descripción + Sintaxis/Ejemplo."""
    command = ctx.command
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
    return e


class WebhookContext(commands.Context):
    """Context que reenvía ctx.send() a través del webhook del bot.
    En DMs no hay webhook posible, así que ahí se manda normal."""

    async def send(self, content=None, **kwargs):
        if self.guild is None:
            return await super().send(content, **kwargs)
        if content is not None:
            kwargs["content"] = content
        return await send_via_webhook(self.channel, **kwargs)


class AntiNukeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=self.get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            owner_ids=self._load_owners(),
        )
        self.db = db
        self._status_index = 0

    def _load_owners(self):
        owners = os.getenv("OWNER_IDS", "")
        if not owners:
            return set()
        return set(int(x.strip()) for x in owners.split(",") if x.strip().isdigit())

    async def get_prefix(self, message):
        if not message.guild:
            return [","]
        guild_data = db.get_guild(message.guild.id)
        prefix = guild_data.get("prefix", DEFAULT_PREFIX)
        return commands.when_mentioned_or(prefix)(self, message)

    async def get_context(self, message, *, cls=WebhookContext):
        return await super().get_context(message, cls=cls)

    async def setup_hook(self):
        cogs = [
            "backup",
            "antinuke",
            "whitelist",
            "moderation",
            "jail",
            "imagedrop",
            "preview",
            "quality_guide",
            "settings",
            "vc_tracker",
            "welcome",
            "autogreet",
            "autorole",
            "autoreact",
            "roblox",
            "info",
            "invites",
            "giveaway",
            "help",
            "lockdown",
            "unban",
            "voice",
            "autosetup",
            "activity_logs",
            "embeds",
            "autoresponder",
            "snipe",
            "premium",
            "emoji_manager",
            "hardban",
            "uid_tracker",
            "boost",
            "vanity_watch",
            "changelog",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded cog: {cog}")
            except Exception as e:
                import traceback
                log.error(f"Failed to load {cog}:\n{traceback.format_exc()}")

    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild and message.content.strip() in (
            f"<@{self.user.id}>", f"<@!{self.user.id}>"
        ):
            guild_data = db.get_guild(message.guild.id)
            prefix = guild_data.get("prefix", DEFAULT_PREFIX)
            embed = discord.Embed(
                description=f"Mi prefijo en este servidor es `{prefix}`\n"
                            f"Usa `{prefix}help` para ver todos los comandos.",
                color=0x2b2d31,
            )
            if message.guild.icon:
                embed.set_thumbnail(url=message.guild.icon.url)
            await message.channel.send(embed=embed)  # respuesta normal, sin webhook
            return

        await self.process_commands(message)

    async def on_ready(self):
        log.info(f"Logged in as {self.user} ({self.user.id})")
        if not self.rotate_status.is_running():
            self.rotate_status.start()

    @tasks.loop(seconds=20)
    async def rotate_status(self):
        statuses = [
            (discord.ActivityType.watching, "nayrux.com"),
            (discord.ActivityType.watching, f"{len(self.guilds)} servidores"),
            (discord.ActivityType.playing, "Mencióname para ver mis comandos"),
            (discord.ActivityType.competing, "seguridad de servidores"),
        ]
        activity_type, name = statuses[self._status_index % len(statuses)]
        self._status_index += 1
        await self.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=activity_type, name=name),
        )

    @rotate_status.before_loop
    async def before_rotate_status(self):
        await self.wait_until_ready()

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            from emojis import REMOVE
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            await ctx.send(embed=discord.Embed(
                description=f"{REMOVE} {ctx.author.mention}: Necesitás el permiso {perms} para usar este comando.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.NotOwner):
            await ctx.send(embed=discord.Embed(
                description="Este comando es solo para el owner.",
                color=0x2b2d31
            ))
        elif isinstance(error, commands.BotMissingPermissions):
            from emojis import REMOVE
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            await ctx.send(embed=discord.Embed(
                description=f"{REMOVE} Necesito el permiso {perms} para ejecutar este comando.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.CheckFailure):
            # Checks propios (p. ej. "solo el dueño del bot o del servidor") traen su mensaje
            await ctx.send(embed=discord.Embed(
                description=str(error) or "No puedes usar este comando.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=build_command_card(ctx))
        else:
            log.error(f"Error en {ctx.command}: {error}")
            await ctx.send(embed=discord.Embed(
                description=f"Ocurrió un error ejecutando el comando: `{error}`",
                color=0xed4245,
            ))


async def main():
    token = os.getenv("TOKEN")
    if not token:
        log.critical("TOKEN environment variable not set.")
        return

    bot = AntiNukeBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
