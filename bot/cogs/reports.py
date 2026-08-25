"""Еженедельные отчёты и подсчёт баллов (п.2), сводка активности (п.3)."""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from core import crud
from core.database import get_session

report_group = app_commands.Group(name="отчёт", description="Еженедельные отчёты сотрудников")


async def work_autocomplete(interaction: discord.Interaction, current: str):
    async with get_session() as session:
        settings = await crud.list_point_settings(session)
    return [
        app_commands.Choice(name=f"{s.title} ({s.points} б.)", value=s.title)
        for s in settings
        if current.lower() in s.title.lower()
    ][:25]


async def _resolve_setting_id(session, title: str | None):
    if not title:
        return None
    settings = await crud.list_point_settings(session)
    for s in settings:
        if s.title == title:
            return s.id
    return None


@report_group.command(name="сдать", description="Сдать свой еженедельный отчёт")
@app_commands.describe(
    текст="Текст отчёта / описание проделанной работы",
    работа1="Вид работы 1", кол_во1="Сколько раз",
    работа2="Вид работы 2", кол_во2="Сколько раз",
    работа3="Вид работы 3", кол_во3="Сколько раз",
)
@app_commands.autocomplete(работа1=work_autocomplete, работа2=work_autocomplete, работа3=work_autocomplete)
async def report_submit(
    interaction: discord.Interaction,
    текст: str,
    работа1: str | None = None,
    кол_во1: int = 1,
    работа2: str | None = None,
    кол_во2: int = 1,
    работа3: str | None = None,
    кол_во3: int = 1,
):
    async with get_session() as session:
        member = await crud.get_member_by_discord_id(session, interaction.user.id)
        if member is None:
            await interaction.response.send_message(
                "❌ Ты не найден в составе отдела (нет привязки Discord-аккаунта). "
                "Обратись к руководству, чтобы тебя добавили через /состав добавить.",
                ephemeral=True,
            )
            return

        items = []
        for title, qty in [(работа1, кол_во1), (работа2, кол_во2), (работа3, кол_во3)]:
            setting_id = await _resolve_setting_id(session, title)
            if setting_id:
                items.append((setting_id, qty))

        report = await crud.submit_weekly_report(session, member.id, items, content=текст)

    await interaction.response.send_message(
        f"✅ Отчёт за неделю с {report.week_start.strftime('%d.%m.%Y')} принят. "
        f"Начислено баллов: **{report.total_points}**.",
        ephemeral=True,
    )


@report_group.command(name="сводка", description="Сводка по отчётам за неделю")
@app_commands.describe(неделя_назад="Сколько недель назад (0 = текущая неделя)")
async def report_summary(interaction: discord.Interaction, неделя_назад: int = 0):
    week_start = crud.week_start_for(dt.date.today()) - dt.timedelta(weeks=неделя_назад)
    async with get_session() as session:
        summary = await crud.weekly_summary(session, week_start)

    if not summary:
        await interaction.response.send_message("Состав пуст — сводка недоступна.")
        return

    submitted = [s for s in summary if s["submitted"]]
    missing = [s for s in summary if not s["submitted"]]

    embed = discord.Embed(
        title=f"Сводка по отчётам — неделя с {week_start.strftime('%d.%m.%Y')}",
        description=f"Сдали: {len(submitted)}/{len(summary)}",
        color=discord.Color.blue(),
    )
    if submitted:
        lines = [f"• **{s['member_name']}** — {s['points']} баллов" for s in sorted(submitted, key=lambda x: -x["points"])]
        embed.add_field(name="✅ Сдали отчёт", value="\n".join(lines)[:1024], inline=False)
    if missing:
        lines = [f"• {s['member_name']}" for s in missing]
        embed.add_field(name="❌ Не сдали отчёт", value="\n".join(lines)[:1024], inline=False)

    await interaction.response.send_message(embed=embed)


class ReportsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(report_group)
    await bot.add_cog(ReportsCog(bot))
