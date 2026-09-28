"""
imagedrop.py — Manda fotos/gifs (ej. links de Pinterest), archivos/fotos
adjuntos, O mensajes REENVIADOS (botón Forward de Discord), por DM al bot, y
elige con botones a cuál canal reenviarlos. Puedes tener varios canales
nombrados (ej. "pfp", "banners", "aesthetic") y el bot te pregunta cuál usar.

Si mandas/reenvías muchas fotos seguidas, el bot espera unos segundos a que
termines, las junta todas (hasta MAX_ITEMS) y te pregunta el canal UNA sola vez.
Las sube de a 10 archivos por mensaje (límite de Discord).

Comandos (dentro del servidor):
  ,addpostchannel <nombre> <#canal>    — agrega/actualiza un canal de destino (manage_guild)
  ,removepostchannel <nombre>          — elimina uno (manage_guild)
  ,postchannels                        — lista los canales configurados
  ,posters add/remove/list <@usuario>  — quién más puede usar esto por DM,
                                          además de quien tenga manage_guild (manage_guild)
  ,post [links] [+ adjuntos]           — postea links y/o archivos desde el server
                                          (te pregunta el canal)

Uso por DM:
  Mándale al bot links, adjunta fotos/archivos o reenvíale mensajes con
  Forward (o combina todo), y te pregunta con botones a cuál canal mandarlos.
"""

import discord
from discord.ext import commands
from config import db
from webhook_utils import send_via_webhook
import re
import asyncio
import logging
import aiohttp

log = logging.getLogger("antinuke.imagedrop")

URL_RE = re.compile(r"https?://\S+")
MAX_ITEMS = 40          # tope de fotos/links por tanda
BATCH_WINDOW = 3        # segundos de silencio antes de preguntar el canal
BUTTON_TIMEOUT = 120
DIRECT_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_META_OG_IMAGE_RE = re.compile(r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]*>', re.IGNORECASE)
_CONTENT_ATTR_RE = re.compile(r'content=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_items(message: discord.Message) -> list[dict]:
    """Junta links + archivos adjuntos de un mensaje, incluyendo los de mensajes
    REENVIADOS con Forward: esos no vienen en message.attachments, sino dentro de
    message.message_snapshots. No aplica tope aquí (lo aplica quien llama)."""
    items = [{"type": "link", "value": url} for url in URL_RE.findall(message.content)]
    items += [{"type": "attachment", "value": att} for att in message.attachments]

    for snap in getattr(message, "message_snapshots", None) or []:
        snap_links = URL_RE.findall(snap.content or "")
        items += [{"type": "link", "value": url} for url in snap_links]
        items += [{"type": "attachment", "value": att} for att in snap.attachments]
        if not snap_links:  # reenvío de un embed con imagen (sin link en el texto)
            for embed in snap.embeds:
                if embed.image and embed.image.url:
                    items.append({"type": "link", "value": embed.image.url})
    return items


async def _resolve_image_url(session: aiohttp.ClientSession, url: str) -> str | None:
    """Si el link ya es una imagen directa, lo regresa tal cual. Si no (ej. una
    página de Pinterest), entra a la página y saca la imagen real del meta
    tag og:image, para no depender de que Discord la adivine."""
    lowered = url.lower().split("?")[0]
    if lowered.endswith(DIRECT_IMAGE_EXTS):
        return url
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), headers={"User-Agent": "Mozilla/5.0"}) as resp:
            if resp.status != 200:
                return None
            html = await resp.text(errors="ignore")
    except Exception as e:
        log.warning(f"No se pudo resolver la imagen de {url}: {e}")
        return None

    tag_match = _META_OG_IMAGE_RE.search(html)
    if not tag_match:
        return None
    content_match = _CONTENT_ATTR_RE.search(tag_match.group(0))
    return content_match.group(1) if content_match else None


def _chunk_attachments(atts: list[discord.Attachment], limit: int) -> list[list[discord.Attachment]]:
    """Agrupa adjuntos en tandas de máx. 10 archivos (límite de Discord por
    mensaje) sin pasarse del peso máximo que acepta el servidor destino."""
    chunks, current, size = [], [], 0
    for att in atts:
        if current and (len(current) >= 10 or size + att.size > limit):
            chunks.append(current)
            current, size = [], 0
        current.append(att)
        size += att.size
    if current:
        chunks.append(current)
    return chunks


async def _send_items(channel: discord.TextChannel, items: list[dict]) -> tuple[int, int]:
    """Sube todo al canal. Devuelve (enviados, omitidos). Los links salen como
    embeds de solo-imagen (de a 10 por mensaje) y los archivos se re-suben tal
    cual, de a 10 por mensaje. Lee los archivos de a una tanda para no llenar
    la memoria con 40 fotos a la vez."""
    limit = channel.guild.filesize_limit
    sent = skipped = 0

    link_urls = [it["value"] for it in items if it["type"] == "link"]
    if link_urls:
        embeds = []
        async with aiohttp.ClientSession() as session:
            for url in link_urls:
                resolved = await _resolve_image_url(session, url)
                embed = discord.Embed()
                embed.set_image(url=resolved or url)
                embeds.append(embed)
        for i in range(0, len(embeds), 10):
            group = embeds[i:i + 10]
            try:
                await send_via_webhook(channel, embeds=group)
                sent += len(group)
            except discord.HTTPException as e:
                log.warning(f"No se pudo postear links en {channel}: {e}")
                skipped += len(group)

    atts = []
    for it in items:
        if it["type"] != "attachment":
            continue
        if it["value"].size > limit:
            skipped += 1  # más pesado de lo que acepta este servidor
        else:
            atts.append(it["value"])

    for chunk in _chunk_attachments(atts, limit):
        files = []
        for att in chunk:
            try:
                files.append(await att.to_file())
            except (discord.HTTPException, discord.Forbidden) as e:
                log.warning(f"No se pudo leer el adjunto {att.filename}: {e}")
                skipped += 1
        if not files:
            continue
        try:
            await send_via_webhook(channel, files=files)
            sent += len(files)
        except discord.HTTPException as e:
            log.warning(f"No se pudo postear archivos en {channel}: {e}")
            skipped += len(files)

    return sent, skipped


def _is_allowed(member: discord.Member, config: dict) -> bool:
    if member.guild_permissions.manage_guild:
        return True
    return member.id in config.get("posters", [])


def _get_post_channels(config: dict) -> dict:
    """Compatibilidad: la versión vieja guardaba un solo 'post_channel_id'."""
    channels = dict(config.get("post_channels", {}))
    legacy_id = config.get("post_channel_id")
    if legacy_id and not channels:
        channels["general"] = legacy_id
    return channels


class ChannelPickView(discord.ui.View):
    """Botones para elegir a cuál canal mandar la tanda de links/archivos."""

    def __init__(self, author_id: int, items: list[dict], options: list[tuple[str, discord.TextChannel]]):
        super().__init__(timeout=BUTTON_TIMEOUT)
        self.author_id = author_id
        self.items = items
        for label, channel in options[:25]:
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(channel)
            self.add_item(button)

    def _make_callback(self, channel: discord.TextChannel):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message("Esto no es para ti.", ephemeral=True)

            await interaction.response.defer()
            sent, skipped = await _send_items(channel, self.items)
            if sent == 0:
                return await interaction.edit_original_response(
                    content=f"No pude mandar eso a {channel.mention}.", embed=None, view=None,
                )

            for item in self.children:
                item.disabled = True
            desc = f"Mandé `{sent}` cosa(s) a {channel.mention}."
            if skipped:
                desc += f"\nNo pude mandar `{skipped}` (muy pesadas para este servidor, o fallaron)."
            await interaction.edit_original_response(
                content=None,
                embed=discord.Embed(description=desc, color=0x57f287),
                view=self,
            )
            self.stop()

        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class ImageDrop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # user_id -> {"items": [...], "dropped": int, "channel": DMChannel, "task": Task}
        self._batches: dict[int, dict] = {}

    # ── DM listener (junta varias fotos seguidas en una sola tanda) ──────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is not None:
            return  # solo nos interesan los DMs

        items = _extract_items(message)
        if not items:
            return

        batch = self._batches.get(message.author.id)
        if batch is None:
            batch = {"items": [], "dropped": 0, "channel": message.channel, "task": None}
            self._batches[message.author.id] = batch

        room = max(MAX_ITEMS - len(batch["items"]), 0)
        batch["items"].extend(items[:room])
        batch["dropped"] += len(items) - min(len(items), room)

        if batch["task"] is not None:
            batch["task"].cancel()  # llegó otra foto: reinicia la espera
        batch["task"] = asyncio.create_task(self._flush_after(message.author.id))

    async def _flush_after(self, user_id: int):
        try:
            await asyncio.sleep(BATCH_WINDOW)
        except asyncio.CancelledError:
            return
        batch = self._batches.pop(user_id, None)
        if batch:
            await self._prompt_channel(user_id, batch)

    async def _prompt_channel(self, user_id: int, batch: dict):
        items = batch["items"]
        options = []
        multi_guild = len([g for g in self.bot.guilds if g.get_member(user_id)]) > 1
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member is None:
                continue
            config = db.get_guild(guild.id)
            if not _is_allowed(member, config):
                continue
            for name, cid in _get_post_channels(config).items():
                channel = guild.get_channel(cid)
                if channel is None:
                    continue
                label = f"{name} — {guild.name}" if multi_guild else name
                options.append((label[:80], channel))

        if not options:
            return  # nadie configuró canales, o no tiene permiso — ignoramos en silencio

        text = f"¿A cuál canal mando esto (`{len(items)}` cosa(s))?"
        if batch["dropped"]:
            text += f"\nEl tope por tanda es `{MAX_ITEMS}`, dejé afuera `{batch['dropped']}`."

        view = ChannelPickView(user_id, items, options)
        await batch["channel"].send(embed=discord.Embed(description=text, color=0x2b2d31), view=view)

    # ── Configuración de canales ─────────────────────────────────────────────

    @commands.command(name="addpostchannel")
    @commands.has_permissions(manage_guild=True)
    async def addpostchannel(self, ctx: commands.Context, name: str, channel: discord.TextChannel):
        name = name.lower().strip()
        config = db.get_guild(ctx.guild.id)
        channels = _get_post_channels(config)
        channels[name] = channel.id
        config["post_channels"] = channels
        config.pop("post_channel_id", None)  # ya migrado
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(
            description=f"Canal `{name}` → {channel.mention}. Cuando mandes links, el bot te preguntará si quieres usar este.",
            color=0x57f287,
        ))

    @commands.command(name="removepostchannel")
    @commands.has_permissions(manage_guild=True)
    async def removepostchannel(self, ctx: commands.Context, name: str):
        name = name.lower().strip()
        config = db.get_guild(ctx.guild.id)
        channels = _get_post_channels(config)
        if name not in channels:
            return await ctx.send(embed=discord.Embed(description=f"No existe un canal llamado `{name}`.", color=0xed4245))
        del channels[name]
        config["post_channels"] = channels
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(description=f"Se eliminó `{name}`.", color=0x57f287))

    @commands.command(name="postchannels")
    async def postchannels(self, ctx: commands.Context):
        config = db.get_guild(ctx.guild.id)
        channels = _get_post_channels(config)
        if not channels:
            desc = "No hay canales configurados. Usa `,addpostchannel <nombre> #canal`."
        else:
            desc = "\n".join(f"`{name}` → <#{cid}>" for name, cid in channels.items())
        await ctx.send(embed=discord.Embed(title="Canales de destino", description=desc, color=0x2b2d31))

    @commands.group(name="posters", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def posters(self, ctx: commands.Context):
        config = db.get_guild(ctx.guild.id)
        ids = config.get("posters", [])
        if not ids:
            desc = "Nadie más tiene acceso — solo quienes ya tienen `Gestionar Servidor`."
        else:
            desc = "\n".join(f"<@{uid}>" for uid in ids)
        await ctx.send(embed=discord.Embed(title="Posters autorizados", description=desc, color=0x2b2d31))

    @posters.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def posters_add(self, ctx: commands.Context, member: discord.Member):
        config = db.get_guild(ctx.guild.id)
        ids = config.get("posters", [])
        if member.id in ids:
            return await ctx.send(embed=discord.Embed(description=f"{member.mention} ya tenía acceso.", color=0x2b2d31))
        ids.append(member.id)
        config["posters"] = ids
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(
            description=f"{member.mention} ahora puede mandar links por DM.",
            color=0x57f287,
        ))

    @posters.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def posters_remove(self, ctx: commands.Context, member: discord.Member):
        config = db.get_guild(ctx.guild.id)
        ids = config.get("posters", [])
        if member.id not in ids:
            return await ctx.send(embed=discord.Embed(description=f"{member.mention} no estaba en la lista.", color=0xed4245))
        ids.remove(member.id)
        config["posters"] = ids
        db.update_guild(ctx.guild.id, config)
        await ctx.send(embed=discord.Embed(description=f"Se quitó el acceso de {member.mention}.", color=0x57f287))

    # ── Comando directo desde el server ─────────────────────────────────────

    @commands.command(name="post")
    async def post(self, ctx: commands.Context):
        config = db.get_guild(ctx.guild.id)
        if not _is_allowed(ctx.author, config):
            return await ctx.send(embed=discord.Embed(
                description="No tienes permiso para usar esto (necesitas `Gestionar Servidor` o estar en `,posters`).",
                color=0xed4245,
            ))

        channels = _get_post_channels(config)
        if not channels:
            return await ctx.send(embed=discord.Embed(
                description="Primero agrega al menos un canal con `,addpostchannel <nombre> #canal`.",
                color=0xed4245,
            ))

        items = _extract_items(ctx.message)[:MAX_ITEMS]
        if not items:
            return await ctx.send(embed=discord.Embed(
                description="Adjunta fotos/archivos y/o pon links junto con `,post`.",
                color=0xed4245,
            ))

        options = []
        for name, cid in channels.items():
            channel = ctx.guild.get_channel(cid)
            if channel:
                options.append((name, channel))

        view = ChannelPickView(ctx.author.id, items, options)
        await ctx.send(
            embed=discord.Embed(description=f"¿A cuál canal mando esto (`{len(items)}` cosa(s))?", color=0x2b2d31),
            view=view,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ImageDrop(bot))
