"""
music.py — Bot de música (estilo Jockie Music) usando Lavalink + wavelink.

A diferencia del intento anterior (yt-dlp + ffmpeg corriendo dentro del
propio bot), este usa Lavalink: un servidor de audio aparte, mantenido
activamente por su propia comunidad específicamente para pelear contra los
bloqueos de YouTube (SABR, verificación anti-bot, etc.) — es el enfoque que
usan los bots de música serios y actualizados en 2026, en vez de pelear esa
guerra nosotros mismos dentro del bot.

Requiere un nodo Lavalink y las variables LAVALINK_URI y LAVALINK_PASSWORD.

Comandos:
  ,play <nombre o link>   — busca/agrega una canción a la cola y la reproduce
  ,skip                   — salta a la siguiente canción
  ,stop                   — detiene todo, vacía la cola y desconecta al bot
  ,pause / ,resume        — pausa o reanuda la canción actual
  ,queue                  — muestra la cola de reproducción
  ,nowplaying             — muestra qué se está reproduciendo ahora
  ,volume <0-200>         — ajusta el volumen
  ,leave                  — desconecta al bot del canal de voz
  ,loop [track|queue|off] — repite la canción actual, la cola entera, o apaga
  ,shuffle                — mezcla el orden de la cola
"""

import logging

import discord
from discord.ext import commands
import wavelink

from voice import EMOJI_SUCCESS, EMOJI_ERROR

log = logging.getLogger("antinuke.music")

IDLE_DISCONNECT_MS = 180_000  # 3 minutos sin nada en cola -> el bot se va solo


def _format_duration(ms: int | None) -> str:
    if not ms:
        return "En vivo / desconocida"
    seconds = int(ms / 1000)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _success_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_SUCCESS} {text}", color=0x57f287)


def _error_embed(text: str) -> discord.Embed:
    return discord.Embed(description=f"{EMOJI_ERROR} {text}", color=0xed4245)


def _track_embed(title: str, track: wavelink.Playable, requester: discord.Member | None = None) -> discord.Embed:
    e = discord.Embed(description=f"[{track.title}]({track.uri})", color=0x2b2d31)
    e.set_author(name=title)
    artwork = getattr(track, "artwork", None)
    if artwork:
        e.set_thumbnail(url=artwork)
    e.add_field(name="Artista", value=track.author or "Desconocido", inline=True)
    e.add_field(name="Duración", value=_format_duration(track.length), inline=True)
    if requester:
        e.add_field(name="Pedido por", value=requester.mention, inline=True)
    return e


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._handling_failures: set[int] = set()
        self._search_alternatives: dict[int, list[wavelink.Playable]] = {}

    async def _edit_feedback(self, track: wavelink.Playable, embed: discord.Embed) -> bool:
        extras = dict(track.extras)
        channel_id = extras.get("feedback_channel_id")
        message_id = extras.get("feedback_message_id")
        if not channel_id or not message_id:
            return False
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return False
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.debug("No se pudo actualizar el mensaje de reproducción", exc_info=True)
            return False

    async def _ensure_voice(self, ctx: commands.Context) -> wavelink.Player | None:
        if ctx.guild is None:
            await ctx.send(embed=_error_embed("La música solo está disponible dentro de servidores."))
            return None
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(embed=_error_embed("Debes estar en un canal de voz para usar esto."))
            return None

        player: wavelink.Player = ctx.guild.voice_client
        channel = ctx.author.voice.channel

        if player is None:
            try:
                player = await channel.connect(cls=wavelink.Player)
            except Exception:
                log.warning("Falló la conexión de voz en el servidor %s", ctx.guild.id, exc_info=True)
                await ctx.send(embed=_error_embed("No pude conectarme al canal de voz. Inténtalo otra vez."))
                return None
            player.autoplay = wavelink.AutoPlayMode.disabled
            player.inactive_timeout = IDLE_DISCONNECT_MS // 1000
        elif player.channel.id != channel.id:
            await ctx.send(embed=_error_embed("Ya estoy reproduciendo en otro canal de voz."))
            return None

        return player

    async def _player_for_ctx(self, ctx: commands.Context) -> wavelink.Player | None:
        if ctx.guild is None:
            await ctx.send(embed=_error_embed("La música solo está disponible dentro de servidores."))
            return None
        player: wavelink.Player = ctx.guild.voice_client
        if player is None:
            await ctx.send(embed=_error_embed("No estoy conectado a un canal de voz."))
            return None
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send(embed=_error_embed("Debes estar en mi canal de voz para controlar la música."))
            return None
        if player.channel.id != ctx.author.voice.channel.id:
            await ctx.send(embed=_error_embed("Debes estar en mi canal de voz para controlar la música."))
            return None
        return player

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        player = await self._ensure_voice(ctx)
        if player is None:
            return

        msg = await ctx.send(embed=discord.Embed(description="Buscando...", color=0x2b2d31))

        is_url = query.startswith(("http://", "https://"))
        is_playlist = False
        if is_url:
            try:
                results = await wavelink.Playable.search(query)
            except Exception:
                log.warning("Falló la búsqueda de música", exc_info=True)
                return await msg.edit(embed=_error_embed("No pude buscar esa canción. Inténtalo de nuevo."))
            tracks = list(results.tracks) if isinstance(results, wavelink.Playlist) else list(results or [])
            is_playlist = isinstance(results, wavelink.Playlist)
        else:
            tracks = []
            sources = (wavelink.TrackSource.YouTube,)
            for source in sources:
                try:
                    found = await wavelink.Playable.search(query, source=source)
                    if found and not isinstance(found, wavelink.Playlist):
                        tracks.extend(found)
                except Exception:
                    log.warning("Falló la búsqueda en %s", source.value, exc_info=True)
            unique_tracks = {}
            for track in tracks:
                unique_tracks.setdefault(track.identifier, track)
            tracks = list(unique_tracks.values())[:6]

        if not tracks:
            return await msg.edit(embed=_error_embed("No encontré ninguna canción con eso."))

        tracks = tracks[:100] if is_playlist else tracks[:6]
        alternatives = [] if is_playlist or is_url else tracks[1:]
        if alternatives:
            tracks = tracks[:1]
        if not tracks:
            return await msg.edit(embed=_error_embed("La lista no contiene canciones disponibles."))
        fallback_query = query if not is_url else f"{tracks[0].title} {tracks[0].author}"
        search_id = msg.id if alternatives else None
        for track in tracks:
            track.extras = {
                "requester_id": ctx.author.id,
                "search_query": fallback_query,
                **({"search_id": search_id} if search_id else {}),
            }
        if search_id:
            self._search_alternatives[search_id] = alternatives

        if not player.playing and not player.paused and player.queue.is_empty:
            track = tracks.pop(0)
            if alternatives:
                self._search_alternatives[ctx.guild.id] = alternatives
            else:
                self._search_alternatives.pop(ctx.guild.id, None)
            track.extras = {
                **dict(track.extras),
                "feedback_channel_id": ctx.channel.id,
                "feedback_message_id": msg.id,
            }
            await player.play(track)
            if tracks:
                await player.queue.put_wait(tracks)
            else:
                await msg.edit(embed=discord.Embed(description="La encontré. Estoy conectando el audio…", color=0x2b2d31))
        else:
            position = player.queue.count + 1
            await player.queue.put_wait(tracks)
            if len(tracks) == 1:
                await msg.edit(embed=_track_embed(f"Agregado a la cola (posición {position})", tracks[0], ctx.author))
            else:
                await msg.edit(embed=_success_embed(f"Añadidas **{len(tracks)} canciones** a la cola desde la posición `{position}`."))

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not player.playing:
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        await player.skip(force=True)
        await ctx.send(embed=_success_embed("Canción saltada."))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        player.queue.clear()
        await player.stop()
        await player.disconnect()
        await ctx.send(embed=_success_embed("Reproducción detenida y cola vaciada."))

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not player.playing:
            return await ctx.send(embed=_error_embed("No hay nada sonando ahora mismo."))
        await player.pause(True)
        await ctx.send(embed=_success_embed("Pausado."))

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not player.paused:
            return await ctx.send(embed=_error_embed("No hay nada pausado ahora mismo."))
        await player.pause(False)
        await ctx.send(embed=_success_embed("Reanudado."))

    @commands.command(name="leave", aliases=["disconnect"])
    async def leave(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        player.queue.clear()
        await player.disconnect()
        await ctx.send(embed=_success_embed("Desconectado del canal de voz."))

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not player.current and player.queue.is_empty:
            return await ctx.send(embed=discord.Embed(description="La cola está vacía.", color=0x2b2d31))

        lines = []
        if player.current:
            lines.append(f"**Ahora:** [{player.current.title}]({player.current.uri})")
        for i, t in enumerate(list(player.queue)[:15], start=1):
            lines.append(f"`{i}.` [{t.title}]({t.uri})")
        extra = player.queue.count - 15
        if extra > 0:
            lines.append(f"...y {extra} más.")

        await ctx.send(embed=discord.Embed(title="Cola de reproducción", description="\n".join(lines), color=0x2b2d31))

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not player.current:
            return await ctx.send(embed=discord.Embed(description="No hay nada reproduciéndose.", color=0x2b2d31))
        await ctx.send(embed=_track_embed("Reproduciendo ahora", player.current))

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx: commands.Context, level: int):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if not 0 <= level <= 200:
            return await ctx.send(embed=_error_embed("El volumen debe estar entre `0` y `200`."))
        await player.set_volume(level)
        await ctx.send(embed=_success_embed(f"Volumen ajustado a `{level}%`."))

    @commands.command(name="loop")
    async def loop_cmd(self, ctx: commands.Context, mode: str = None):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        mode = (mode or "").lower()
        mapping = {
            "track": wavelink.QueueMode.loop,
            "queue": wavelink.QueueMode.loop_all,
            "off": wavelink.QueueMode.normal,
        }
        if mode not in mapping:
            return await ctx.send(embed=_error_embed("Usa `,loop track`, `,loop queue`, o `,loop off`."))
        player.queue.mode = mapping[mode]
        labels = {"track": "canción actual", "queue": "cola completa", "off": "desactivado"}
        await ctx.send(embed=_success_embed(f"Repetición: **{labels[mode]}**."))

    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context):
        player = await self._player_for_ctx(ctx)
        if not player:
            return
        if player.queue.is_empty:
            return await ctx.send(embed=_error_embed("No hay suficientes canciones en la cola para mezclar."))
        player.queue.shuffle()
        await ctx.send(embed=_success_embed("Cola mezclada."))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if payload.reason != "loadFailed":
            search_id = dict(payload.track.extras).get("search_id")
            if search_id:
                self._search_alternatives.pop(search_id, None)
        if player is None or payload.reason in {"replaced", "loadFailed"} or player.queue.is_empty:
            return
        next_track = await player.queue.get_wait()
        await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        track = payload.track
        search_id = dict(track.extras).get("search_id")
        if search_id:
            self._search_alternatives.pop(search_id, None)
        await self._edit_feedback(track, _track_embed("Reproduciendo ahora", track))

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        if player.queue.is_empty and not player.playing:
            await player.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        track = payload.track
        player = payload.player
        if player is None:
            return

        guild_id = player.guild.id
        if guild_id in self._handling_failures:
            return
        self._handling_failures.add(guild_id)
        try:
            log.warning("Lavalink no pudo reproducir %s (%s): %s", track.title, track.source, payload.exception)
            extras = dict(track.extras)
            tried_fallback = extras.get("soundcloud_fallback", False)

            search_id = extras.get("search_id")
            candidates = self._search_alternatives.get(search_id, [])
            if track.source == "youtube" and candidates:
                alternative = candidates.pop(0)
                alternative.extras = {
                    **dict(alternative.extras),
                    **extras,
                }
                await self._edit_feedback(
                    alternative,
                    discord.Embed(description="Esta versión requiere acceso. Pruebo otra…", color=0x2b2d31),
                )
                await player.play(alternative)
                return

            if track.source == "youtube" and not tried_fallback:
                title_artist = f"{track.title} {track.author}".strip()
                queries = list(dict.fromkeys((title_artist, extras.get("search_query", ""))))
                alternatives = []
                for query in queries:
                    if not query:
                        continue
                    try:
                        results = await wavelink.Playable.search(
                            query,
                            source=wavelink.TrackSource.SoundCloud,
                        )
                        alternatives = list(results.tracks) if isinstance(results, wavelink.Playlist) else list(results or [])
                    except Exception:
                        log.warning("Falló la búsqueda alternativa en SoundCloud (%s)", query, exc_info=True)
                    if alternatives:
                        break

                if alternatives:
                    alternative = alternatives[0]
                    alternative.extras = {
                        "requester_id": extras.get("requester_id"),
                        "search_query": query,
                        "soundcloud_fallback": True,
                        "feedback_channel_id": extras.get("feedback_channel_id"),
                        "feedback_message_id": extras.get("feedback_message_id"),
                        "search_id": search_id,
                    }
                    await player.play(alternative)
                    if player.channel:
                        await player.channel.send(embed=_success_embed("YouTube bloqueó esa pista; probando una copia de SoundCloud."))
                    return
                if search_id:
                    self._search_alternatives.pop(search_id, None)

            channel = self.bot.get_channel(extras.get("feedback_channel_id")) if extras.get("feedback_channel_id") else player.channel
            if channel:
                detail = "No pude transmitir esa pista desde YouTube ni encontrar una copia en SoundCloud." if track.source == "youtube" else "La fuente de audio no pudo transmitir esta pista. Prueba otra búsqueda."
                error_embed = _error_embed(detail)
                updated = await self._edit_feedback(track, error_embed)
                if not updated:
                    await channel.send(embed=error_embed)

            if not player.queue.is_empty:
                await player.play(await player.queue.get_wait())
            else:
                await player.stop()
        finally:
            self._handling_failures.discard(guild_id)

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        log.warning("Pista bloqueada en Lavalink (%s ms)", payload.threshold)
        player = payload.player
        if player is not None:
            await player.stop()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        log.info(f"Nodo de Lavalink conectado: {payload.node.identifier} (session {payload.session_id})")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
