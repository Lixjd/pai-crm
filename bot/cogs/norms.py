"""Дневная норма: 1 час в холле + 1 гос. волна (п.5)."""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from core.config import ADMIN_ROLE_IDS
from core import crud
from core.database import get_session

norm_group = app_commands.Group(name="норма", description="Дневная норма сотрудников (холл + гос. волна)")


def _user_is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    if not ADMIN_ROLE_IDS:
        return True
    user_role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
    return bool(user_role_ids & ADMIN_ROLE_IDS)


@norm_group.command(name="отметить", description="Отметить выполнение нормы за сегодня (себе) или сотруднику (админ)")
@app_commands.describe(холл="Отстоял час в холле", волна="Откинул гос. волну", static="Static ID сотрудника (для админа, необязательно)")
async def norm_mark(
    interaction: discord.Interaction,
    холл: bool | None = None,
    волна: bool | None = None,
    static: str | None = None,
):
    if static and not _user_is_admin(interaction):
        await interaction.response.send_message(
            "❌ Отмечать норму за другого сотрудника могут только руководители.", ephemeral=True
        )
        return

    async with get_session() as session:
        if static:
            member = await crud.get_member_by_static(session, static)
        else:
            member = await crud.get_member_by_discord_id(session, interaction.user.id)

        if member is None:
            await interaction.response.send_message("❌ Сотрудник не найден.", ephemeral=True)
            return

        norm = await crud.set_daily_norm(
            session, member.id, dt.date.today(), hall_hour_done=холл, gov_wave_done=волна
        )

    status = "✅ выполнена" if norm.completed else "⏳ не полностью"
    await interaction.response.send_message(
        f"Норма на {dt.date.today().strftime('%d.%m.%Y')} для **{member.full_name}**: {status}\n"
        f"Холл: {'✅' if norm.hall_hour_done else '❌'} · Гос. волна: {'✅' if norm.gov_wave_done else '❌'}"
    )


@norm_group.command(name="таблица", description="Таблица выполнения нормы за диапазон дней")
@app_commands.describe(дней="За сколько последних дней показать (по умолчанию 7)")
async def norm_table(interaction: discord.Interaction, дней: int = 7):
    end = dt.date.today()
    start = end - dt.timedelta(days=дней - 1)
    async with get_session() as session:
        table = await crud.norms_table(session, start, end)

    if not table["rows"]:
        await interaction.response.send_message("Состав пуст.")
        return

    lines = []
    for row in table["rows"]:
        marks = "".join("🟩" if row["days"][d]["completed"] else "🟥" for d in table["days"])
        lines.append(f"{marks}  **{row['member_name']}**")

    embed = discord.Embed(
        title=f"Норма: {start.strftime('%d.%m')} — {end.strftime('%d.%m')}",
        description="\n".join(lines)[:4000],
        color=discord.Color.green(),
    )
    embed.set_footer(text="🟩 норма выполнена полностью · 🟥 не выполнена")
    await interaction.response.send_message(embed=embed)


class NormsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(norm_group)
    await bot.add_cog(NormsCog(bot))
