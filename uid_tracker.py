"""
uid_tracker.py — Historial de usuario: nombres, avatares y detección de Nitro.

Escucha on_user_update (evento global, no por servidor — el username y avatar
de Discord son de la cuenta, no del server) y va guardando cada cambio. El
comando ,uid muestra un panel con 3 vistas: Ficha, Nombres, Avatares.

Limitaciones honestas:
- El historial arranca vacío desde que se instala esto — no hay forma de
  recuperar cambios de nombre/avatar de ANTES de tener este código corriendo,
  esa info no existe en ningún lado accesible por la API de Discord.
- "Nitro detectado" es un HEURÍSTICO (avatar animado o decoración de avatar
  presente), no un dato oficial — Discord no le da a los bots si un usuario
  tiene Nitro ni desde cuándo. No mostramos fecha de renovación porque no
  existe forma de saberla.
- El tiempo de "boost a este servidor" (member.premium_since) sí es 100%
  preciso y oficial.
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone
from config import db
import aiohttp
import io


def _has_nitro_indicators(user: discord.User) -> bool:
    if user.avatar and user.avatar.is_animated():
        return True
    if getattr(user, "avatar_decoration", None):
        return True
    return False


class UidTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        data = db.get_user(after.id)
        changed = False

        if before.name != after.name:
            data.setdefault("usernames", []).append({
                "name": after.name,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            changed = True

        if before.display_avatar.key != after.display_avatar.key:
            data.setdefault("avatars", []).append({
                "url": after.display_avatar.url,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            changed = True

        if not data.get("nitro_detected_at") and _has_nitro_indicators(after):
            data["nitro_detected_at"] = datetime.now(timezone.utc).isoformat()
            changed = True

        if changed:
            db.update_user(after.id, data)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # primera vez que vemos a este usuario: sembrar el historial con lo que ya tiene
        data = db.get_user(member.id)
        if not data.get("usernames"):
            data["usernames"] = [{"name": member.name, "at": datetime.now(timezone.utc).isoformat()}]
        if not data.get("avatars"):
            data["avatars"] = [{"url": member.display_avatar.url, "at": datetime.now(timezone.utc).isoformat()}]
        if not data.get("nitro_detected_at") and _has_nitro_indicators(member):
            data["nitro_detected_at"] = datetime.now(timezone.utc).isoformat()
        db.update_user(member.id, data)

    # ── Comando ,uid ─────────────────────────────────────────────────────────

    @commands.command(name="uid")
    async def uid(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = db.get_user(member.id)
        view = UidView(self.bot, member, data)
        embed = view.build_ficha()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="names")
    async def names_cmd(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = db.get_user(member.id)
        view = UidView(self.bot, member, data)
        view.active = "nombres"
        view._render()
        embed = view.build_nombres()
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="avatars", aliases=["avatares"])
    async def avatars_cmd(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = db.get_user(member.id)
        view = UidView(self.bot, member, data)
        view.active = "avatares"
        view._render()
        embed, file = await view.build_avatares()
        view.message = await ctx.send(embed=embed, file=file, view=view) if file else await ctx.send(embed=embed, view=view)


def _rel(iso_str: str | None) -> str:
    if not iso_str:
        return "No detectado"
    dt = datetime.fromisoformat(iso_str)
    return discord.utils.format_dt(dt, "R")


NAMES_PAGE_SIZE = 10
AVATARS_PAGE_SIZE = 9


class UidSelect(discord.ui.Select):
    def __init__(self, outer: "UidView"):
        self.outer = outer
        options = [
            discord.SelectOption(label="Ficha", value="ficha", emoji="🪪"),
            discord.SelectOption(label="Nombres", value="nombres", emoji="📛"),
            discord.SelectOption(label="Avatares", value="avatares", emoji="🖼️"),
        ]
        super().__init__(placeholder="Ficha", options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.outer
        view.active = self.values[0]
        if view.active == "ficha":
            view._render()
            await interaction.response.edit_message(embed=view.build_ficha(), attachments=[], view=view)
        elif view.active == "nombres":
            view.names_page = 0
            view._render()
            await interaction.response.edit_message(embed=view.build_nombres(), attachments=[], view=view)
        else:
            view.avatars_page = 0
            view._render()
            await interaction.response.defer()
            embed, file = await view.build_avatares()
            kwargs = {"attachments": [file]} if file else {"attachments": []}
            await interaction.edit_original_response(embed=embed, view=view, **kwargs)


class PageButton(discord.ui.Button):
    def __init__(self, outer: "UidView", label: str, delta: int | None, style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style, row=1)
        self.outer = outer
        self.delta = delta  # None = botón "cerrar"

    async def callback(self, interaction: discord.Interaction):
        view = self.outer
        if self.delta is None:
            for item in view.children:
                item.disabled = True
            return await interaction.response.edit_message(view=view)

        total = view._total_pages()
        if self.delta == 0:
            page = 0
        elif self.delta == 999:
            page = total - 1
        else:
            page = view._current_page() + self.delta
        page = max(0, min(total - 1, page))
        view._set_page(page)
        view._render()

        if view.active == "nombres":
            await interaction.response.edit_message(embed=view.build_nombres(), attachments=[], view=view)
        else:
            await interaction.response.defer()
            embed, file = await view.build_avatares()
            kwargs = {"attachments": [file]} if file else {"attachments": []}
            await interaction.edit_original_response(embed=embed, view=view, **kwargs)


class UidView(discord.ui.View):
    def __init__(self, bot: commands.Bot, member: discord.Member, data: dict):
        super().__init__(timeout=120)
        self.bot = bot
        self.member = member
        self.data = data
        self.message: discord.Message | None = None
        self.active = "ficha"
        self.names_page = 0
        self.avatars_page = 0
        self._render()

    def _total_pages(self) -> int:
        if self.active == "nombres":
            n = len(self.data.get("usernames", []))
            size = NAMES_PAGE_SIZE
        else:
            n = len(self.data.get("avatars", []))
            size = AVATARS_PAGE_SIZE
        return max(1, (n + size - 1) // size)

    def _current_page(self) -> int:
        return self.names_page if self.active == "nombres" else self.avatars_page

    def _set_page(self, page: int):
        if self.active == "nombres":
            self.names_page = page
        else:
            self.avatars_page = page

    def _render(self):
        self.clear_items()
        self.add_item(UidSelect(self))
        if self.active in ("nombres", "avatares") and self._total_pages() > 1:
            self.add_item(PageButton(self, "«", 0, discord.ButtonStyle.secondary))
            self.add_item(PageButton(self, "‹", -1, discord.ButtonStyle.secondary))
            self.add_item(PageButton(self, "✕", None, discord.ButtonStyle.danger))
            self.add_item(PageButton(self, "›", 1, discord.ButtonStyle.secondary))
            self.add_item(PageButton(self, "»", 999, discord.ButtonStyle.secondary))

    async def on_timeout(self):
        if self.message is None:
            return
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    def build_ficha(self) -> discord.Embed:
        m = self.member
        e = discord.Embed(title=str(m), color=m.color if m.color.value else 0x2b2d31)
        e.set_thumbnail(url=m.display_avatar.url)

        e.add_field(name="Nitro", value=f"Detectado {_rel(self.data.get('nitro_detected_at'))}", inline=False)

        if m.premium_since:
            e.add_field(
                name="Boost a este servidor",
                value=discord.utils.format_dt(m.premium_since, "R"),
                inline=False,
            )

        e.add_field(name="Creado", value=discord.utils.format_dt(m.created_at, "R"), inline=True)
        e.add_field(name="Se unió", value=discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—", inline=True)
        top_role = m.top_role.mention if m.top_role and m.top_role.name != "@everyone" else "Ninguno"
        e.add_field(name="Rol más alto", value=top_role, inline=True)

        e.description = f"[Avatar]({m.display_avatar.url})"
        e.set_footer(text=f"ID: {m.id}")
        return e

    def build_nombres(self) -> discord.Embed:
        history = list(reversed(self.data.get("usernames", [])))
        total_pages = self._total_pages()
        start = self.names_page * NAMES_PAGE_SIZE
        page_items = history[start:start + NAMES_PAGE_SIZE]

        e = discord.Embed(title=f"Historial de nombres de {self.member}", color=0x2b2d31)
        if not history:
            e.description = "Sin cambios de nombre registrados todavía."
        else:
            lines = [f"`{start + i + 1}.` **{h['name']}** · {_rel(h['at'])}" for i, h in enumerate(page_items)]
            e.description = "\n".join(lines)
        e.set_footer(text=f"Página {self.names_page + 1}/{total_pages} ({len(history)} registros)")
        return e

    async def build_avatares(self) -> tuple[discord.Embed, discord.File | None]:
        history = list(reversed(self.data.get("avatars", [])))
        total_pages = self._total_pages()
        start = self.avatars_page * AVATARS_PAGE_SIZE
        page_items = history[start:start + AVATARS_PAGE_SIZE]

        e = discord.Embed(title=f"Historial de avatares de {self.member}", color=0x2b2d31)
        e.set_footer(text=f"Página {self.avatars_page + 1}/{total_pages} ({len(history)} registros)")

        if not page_items:
            e.description = "Sin cambios de avatar registrados todavía."
            return e, None

        collage = await self._build_collage([h["url"] for h in page_items])
        if collage is None:
            e.description = "\n".join(f"[Avatar {start + i + 1}]({h['url']})" for i, h in enumerate(page_items))
            return e, None

        file = discord.File(collage, filename="avatares.png")
        e.set_image(url="attachment://avatares.png")
        return e, file

    async def _build_collage(self, urls: list[str]) -> io.BytesIO | None:
        try:
            from PIL import Image
        except ImportError:
            return None

        size = 128
        cols = 3
        rows = (len(urls) + cols - 1) // cols
        canvas = Image.new("RGBA", (size * cols, size * rows), (0, 0, 0, 0))

        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(urls):
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        raw = await resp.read()
                    img = Image.open(io.BytesIO(raw)).convert("RGBA").resize((size, size))
                    x, y = (i % cols) * size, (i // cols) * size
                    canvas.paste(img, (x, y))
                except Exception:
                    continue

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        buf.seek(0)
        return buf 


async def setup(bot: commands.Bot):
    await bot.add_cog(UidTracker(bot))
