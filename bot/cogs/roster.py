"""Состав отдела: добавление, удаление, редактирование, список."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import is_admin
from core import crud
from core.database import get_session
from core.models import Position

POSITION_CHOICES = [app_commands.Choice(name=p.value, value=p.name) for p in Position]

roster_group = app_commands.Group(name="состав", description="Управление составом отдела PAI")


@roster_group.command(name="добавить", description="Добавить сотрудника в состав")
@app_commands.describe(
    имя="Имя",
    фамилия="Фамилия",
    static="Static ID",
    должность="Должность в отделе",
    участник="Связанный Discord-пользователь (необязательно)",
)
@app_commands.choices(должность=POSITION_CHOICES)
@is_admin()
async def roster_add(
    interaction: discord.Interaction,
    имя: str,
    фамилия: str,
    static: str,
    должность: app_commands.Choice[str],
    участник: discord.Member | None = None,
):
    async with get_session() as session:
        existing = await crud.get_member_by_static(session, static)
        if existing is not None:
            await interaction.response.send_message(
                f"❌ Сотрудник со static `{static}` уже есть в составе: {existing.full_name}.",
                ephemeral=True,
            )
            return
        member = await crud.add_member(
            session,
            first_name=имя,
            last_name=фамилия,
            static_id=static,
            position=Position[должность.value],
            discord_id=участник.id if участник else None,
        )
    await interaction.response.send_message(
        f"✅ Добавлен в состав: **{member.full_name}** ({member.position.value}), static `{member.static_id}`."
    )


@roster_group.command(name="удалить", description="Удалить сотрудника из состава")
@app_commands.describe(static="Static ID сотрудника", навсегда="Удалить без возможности восстановления")
@is_admin()
async def roster_remove(interaction: discord.Interaction, static: str, навсегда: bool = False):
    async with get_session() as session:
        member = await crud.get_member_by_static(session, static)
        if member is None:
            await interaction.response.send_message(f"❌ Сотрудник со static `{static}` не найден.", ephemeral=True)
            return
        name = member.full_name
        await crud.remove_member(session, member.id, hard=навсегда)
    await interaction.response.send_message(f"✅ **{name}** удалён из состава.")


@roster_group.command(name="изменить", description="Изменить данные сотрудника")
@app_commands.describe(
    static="Static ID сотрудника, которого редактируем",
    имя="Новое имя",
    фамилия="Новая фамилия",
    новый_static="Новый static ID",
    должность="Новая должность",
)
@app_commands.choices(должность=POSITION_CHOICES)
@is_admin()
async def roster_edit(
    interaction: discord.Interaction,
    static: str,
    имя: str | None = None,
    фамилия: str | None = None,
    новый_static: str | None = None,
    должность: app_commands.Choice[str] | None = None,
):
    async with get_session() as session:
        member = await crud.get_member_by_static(session, static)
        if member is None:
            await interaction.response.send_message(f"❌ Сотрудник со static `{static}` не найден.", ephemeral=True)
            return
        updated = await crud.update_member(
            session,
            member.id,
            first_name=имя,
            last_name=фамилия,
            static_id=новый_static,
            position=Position[должность.value] if должность else None,
        )
    await interaction.response.send_message(f"✅ Данные обновлены: **{updated.full_name}** ({updated.position.value}).")


@roster_group.command(name="список", description="Показать весь состав отдела")
@app_commands.describe(должность="Отфильтровать по должности (необязательно)")
@app_commands.choices(должность=POSITION_CHOICES)
async def roster_list(interaction: discord.Interaction, должность: app_commands.Choice[str] | None = None):
    async with get_session() as session:
        members = await crud.list_members(session)
    if должность:
        members = [m for m in members if m.position == Position[должность.value]]

    if not members:
        await interaction.response.send_message("Состав пуст.")
        return

    by_position: dict[str, list] = {}
    for m in members:
        by_position.setdefault(m.position.value, []).append(m)

    embed = discord.Embed(title="Состав отдела PAI", color=discord.Color.dark_teal())
    for pos in Position:
        group = by_position.get(pos.value)
        if not group:
            continue
        lines = [f"• **{m.full_name}** — static `{m.static_id}`" for m in group]
        embed.add_field(name=f"{pos.value} ({len(group)})", value="\n".join(lines), inline=False)

    await interaction.response.send_message(embed=embed)


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(roster_group)
    await bot.add_cog(RosterCog(bot))
