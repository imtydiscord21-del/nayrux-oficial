# ai_chat.py
# Cog para integrar una IA (OpenAI-compatible) al bot. Responde en un canal
# configurado, o cuando se menciona al bot, o por DM.
#
# Instalación:
#   pip install aiohttp
#
# Variables de entorno (opcionales si usás la key hardcodeada de abajo):
#   AI_API_KEY   -> tu API key (OpenAI, Groq, OpenRouter, etc.)
#   AI_BASE_URL  -> (opcional) default: https://api.openai.com/v1
#   AI_MODEL     -> (opcional) default: gpt-4o-mini
#
# Comandos:
#   ,ai <mensaje>              — consulta rápida (responde en el mismo canal)
#   ,ai setup <#canal>         — define el canal donde la IA responde a todo
#   ,ai off                    — desactiva el canal de IA
#   ,ai status                 — muestra la config actual
#   ,ai persona <texto>        — define el system prompt / personalidad
#   ,ai reset                  — limpia el historial del canal actual
#   ,ai clearhistory           — limpia el historial de todos los canales
#
# Cómo se activa la respuesta automática:
#   1) Si el mensaje viene en el canal configurado con ,ai setup
#   2) Si mencionan al bot en cualquier canal
#   3) Si el autor le manda DM al bot

import os
import aiohttp
import discord
from discord.ext import commands
from config import db
import logging

log = logging.getLogger("antinuke.ai_chat")

# ── API key hardcodeada (fallback si no hay variable de entorno) ───────────
HARDCODED_API_KEY = "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"

AI_API_KEY = os.getenv("AI_API_KEY", HARDCODED_API_KEY)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

MAX_HISTORY = 12          # mensajes previos que se mandan como contexto
MAX_TOKENS = 500          # límite de tokens de la respuesta
REQUEST_TIMEOUT = 45      # segundos
DEFAULT_PERSONA = "Eres un asistente útil, directo y conciso. Responde en español."


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        # historial en memoria: {channel_id: [{"role": ..., "content": ...}, ...]}
        self.history: dict[int, list[dict]] = {}

    async def cog_load(self):
        if AI_API_KEY:
            self.session = aiohttp.ClientSession()
            log.info(f"AI Chat listo (modelo={AI_MODEL}, base={AI_BASE_URL})")
        else:
            log.warning("AI_API_KEY no configurada — el cog ,ai quedará inactivo.")

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    # ── Lógica interna ──────────────────────────────────────────────────────

    def _get_ai_config(self, guild_id: int) -> dict:
        config = db.get_guild(guild_id)
        return config.get("ai_chat", {"channel_id": None, "persona": DEFAULT_PERSONA})

    def _save_ai_config(self, guild_id: int, ai_config: dict):
        config = db.get_guild(guild_id)
        config["ai_chat"] = ai_config
        db.update_guild(guild_id, config)

    async def _ask_ai(self, channel_id: int, user_message: str, persona: str) -> str:
        """Manda el mensaje a la API y devuelve la respuesta como texto."""
        if not self.session:
            return "La IA no está configurada (falta `AI_API_KEY`)."

        history = self.history.setdefault(channel_id, [])
        messages = [{"role": "system", "content": persona}]
        messages.extend(history[-MAX_HISTORY:])
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with self.session.post(
                f"{AI_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    err = data.get("error", {}).get("message", str(data))
                    log.error(f"AI API error {resp.status}: {err}")
                    return f"Error de la API de IA: `{err}`"
                reply = data["choices"][0]["message"]["content"].strip()
        except aiohttp.ClientError as e:
            log.error(f"AI request failed: {e}")
            return "No pude contactar a la IA en este momento."
        except Exception as e:
            log.error(f"AI unexpected error: {e}")
            return "Ocurrió un error consultando a la IA."

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY * 2:
            del history[:-MAX_HISTORY * 2]

        return reply

    @staticmethod
    def _split(text: str, limit: int = 1900) -> list[str]:
        return [text[i:i + limit] for i in range(0, len(text), limit)] or [""]

    # ── Respuesta automática ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not AI_API_KEY or not self.session:
            return
        if message.content.startswith(tuple(await self.bot.get_prefix(message))):
            return  # deja pasar comandos al handler normal

        persona = DEFAULT_PERSONA
        content = message.content

        if message.guild:
            ai_cfg = self._get_ai_config(message.guild.id)
            persona = ai_cfg.get("persona") or DEFAULT_PERSONA

            is_ai_channel = ai_cfg.get("channel_id") == message.channel.id
            mentions_bot = self.bot.user in message.mentions

            if not (is_ai_channel or mentions_bot):
                return

            if mentions_bot:
                content = (
                    content.replace(f"<@{self.bot.user.id}>", "")
                    .replace(f"<@!{self.bot.user.id}>", "")
                    .strip()
                )
                if not content:
                    return
        else:
            # DM al bot
            pass

        async with message.channel.typing():
            reply = await self._ask_ai(message.channel.id, content, persona)

        for chunk in self._split(reply):
            await message.channel.send(chunk)

    # ── Comandos ────────────────────────────────────────────────────────────

    @commands.group(name="ai", invoke_without_command=True)
    async def ai_group(self, ctx: commands.Context, *, prompt: str = None):
        """Consulta directa a la IA: ,ai <pregunta>"""
        if not AI_API_KEY or not self.session:
            return await ctx.send(embed=discord.Embed(
                description="La IA no está configurada. Falta `AI_API_KEY` en el entorno.",
                color=0xed4245,
            ))
        if not prompt:
            return await ctx.send(embed=discord.Embed(
                description="Usa `,ai <pregunta>`. Subcomandos: `setup`, `off`, `status`, `persona`, `reset`, `clearhistory`.",
                color=0x2b2d31,
            ))

        persona = DEFAULT_PERSONA
        if ctx.guild:
            persona = self._get_ai_config(ctx.guild.id).get("persona") or DEFAULT_PERSONA

        async with ctx.typing():
            reply = await self._ask_ai(ctx.channel.id, prompt, persona)

        for chunk in self._split(reply):
            await ctx.send(chunk)

    @ai_group.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def ai_setup(self, ctx: commands.Context, channel: discord.TextChannel):
        """Define el canal donde la IA responde a cada mensaje."""
        if not ctx.guild:
            return
        cfg = self._get_ai_config(ctx.guild.id)
        cfg["channel_id"] = channel.id
        self._save_ai_config(ctx.guild.id, cfg)
        await ctx.send(embed=discord.Embed(
            description=f"IA activada en {channel.mention}. Ahora responde a todos los mensajes ahí.",
            color=0x57f287,
        ))

    @ai_group.command(name="off")
    @commands.has_permissions(administrator=True)
    async def ai_off(self, ctx: commands.Context):
        """Desactiva el canal de IA."""
        if not ctx.guild:
            return
        cfg = self._get_ai_config(ctx.guild.id)
        cfg["channel_id"] = None
        self._save_ai_config(ctx.guild.id, cfg)
        await ctx.send(embed=discord.Embed(
            description="Canal de IA desactivado. Seguirá respondiendo a menciones y DMs.",
            color=0x57f287,
        ))

    @ai_group.command(name="status")
    async def ai_status(self, ctx: commands.Context):
        """Muestra la configuración actual de la IA."""
        if not ctx.guild:
            return
        cfg = self._get_ai_config(ctx.guild.id)
        ch = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "`no configurado`"
        persona = (cfg.get("persona") or DEFAULT_PERSONA)[:200]
        embed = discord.Embed(title="Estado de la IA", color=0x2b2d31)
        embed.add_field(name="API", value="`activa`" if (AI_API_KEY and self.session) else "`inactiva (falta API key)`", inline=False)
        embed.add_field(name="Modelo", value=f"`{AI_MODEL}`", inline=True)
        embed.add_field(name="Base URL", value=f"`{AI_BASE_URL}`", inline=True)
        embed.add_field(name="Canal", value=ch, inline=False)
        embed.add_field(name="Persona", value=f"```{persona}```", inline=False)
        await ctx.send(embed=embed)

    @ai_group.command(name="persona")
    @commands.has_permissions(administrator=True)
    async def ai_persona(self, ctx: commands.Context, *, text: str = None):
        """Define el system prompt / personalidad de la IA en este servidor."""
        if not ctx.guild:
            return
        cfg = self._get_ai_config(ctx.guild.id)
        if not text:
            return await ctx.send(embed=discord.Embed(
                description="Uso: `,ai persona <texto>`. Usa `reset` para volver a la por defecto.",
                color=0x2b2d31,
            ))
        cfg["persona"] = text.strip()
        self._save_ai_config(ctx.guild.id, cfg)
        await ctx.send(embed=discord.Embed(
            description="Persona actualizada.",
            color=0x57f287,
        ))

    @ai_group.command(name="reset")
    async def ai_reset(self, ctx: commands.Context):
        """Borra el historial de conversación del canal actual."""
        self.history.pop(ctx.channel.id, None)
        await ctx.send(embed=discord.Embed(
            description="Historial de este canal borrado.",
            color=0x57f287,
        ))

    @ai_group.command(name="clearhistory")
    @commands.has_permissions(administrator=True)
    async def ai_clearhistory(self, ctx: commands.Context):
        """Borra el historial de conversación de todos los canales."""
        self.history.clear()
        await ctx.send(embed=discord.Embed(
            description="Historial de todos los canales borrado.",
            color=0x57f287,
        ))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=discord.Embed(
                description="Necesitás ser administrador para usar ese subcomando.",
                color=0xed4245,
            ))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(
                description=f"Falta un argumento: `{error.param.name}`.",
                color=0xed4245,
            ))
        else:
            log.error(f"Error en ai cog: {error}")
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
