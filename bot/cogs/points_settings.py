"""Настройки видов работ и баллов за них (используются в еженедельных отчётах)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import is_admin
from core import crud
from core.database import get_session

points_group = app_commands.Group(name="баллы-настройка", description="Настройка видов работ и баллов за них")


@points_group.command(name="добавить", description="Добавить вид работы и количество баллов за неё")
@app_commands.describe(название="Название работы (например: 'Патруль')", баллы="Количество баллов за одну единицу")
@is_admin()
async def points_add(interaction: discord.Interaction, название: str, баллы: int):
    async with get_session() as session:
        setting = await crud.add_point_setting(session, title=название, points=баллы)
    await interaction.response.send_message(f"✅ Добавлено: **{setting.title}** — {setting.points} баллов.")


@points_group.command(name="изменить", description="Изменить название или баллы существующего вида работы")
@app_commands.describe(id="ID вида работы (смотри /баллы-настройка список)", название="Новое название", баллы="Новое кол-во баллов")
@is_admin()
async def points_edit(interaction: discord.Interaction, id: int, название: str | None = None, баллы: int | None = None):
    async with get_session() as session:
        setting = await crud.update_point_setting(session, id, title=название, points=баллы)
    if setting is None:
        await interaction.response.send_message("❌ Вид работы с таким ID не найден.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Обновлено: **{setting.title}** — {setting.points} баллов.")


@points_group.command(name="удалить", description="Удалить вид работы из настроек")
@app_commands.describe(id="ID вида работы")
@is_admin()
async def points_remove(interaction: discord.Interaction, id: int):
    async with get_session() as session:
        ok = await crud.remove_point_setting(session, id)
    if not ok:
        await interaction.response.send_message("❌ Вид работы с таким ID не найден.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Вид работы удалён из настроек.")


@points_group.command(name="список", description="Показать все виды работ и баллы за них")
async def points_list(interaction: discord.Interaction):
    async with get_session() as session:
        settings = await crud.list_point_settings(session)
    if not settings:
        await interaction.response.send_message("Список видов работ пуст. Добавьте их через /баллы-настройка добавить.")
        return
    embed = discord.Embed(title="Виды работ и баллы", color=discord.Color.gold())
    for s in settings:
        embed.add_field(name=f"#{s.id} — {s.title}", value=f"{s.points} баллов", inline=False)
    await interaction.response.send_message(embed=embed)


class PointsSettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(points_group)
    await bot.add_cog(PointsSettingsCog(bot))
