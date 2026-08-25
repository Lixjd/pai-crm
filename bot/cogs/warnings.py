"""Выговоры: 1 варн, 2 варна, понижение (п.4)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import is_admin
from core import crud
from core.database import get_session
from core.models import WarningLevel

LEVEL_CHOICES = [app_commands.Choice(name=lvl.value, value=lvl.name) for lvl in WarningLevel]

warn_group = app_commands.Group(name="выговор", description="Выдача выговоров сотрудникам")


@warn_group.command(name="выдать", description="Выдать выговор сотруднику")
@app_commands.describe(static="Static ID сотрудника", уровень="1 варн / 2 варна / Понижение", причина="Причина выговора")
@app_commands.choices(уровень=LEVEL_CHOICES)
@is_admin()
async def warn_issue(
    interaction: discord.Interaction,
    static: str,
    уровень: app_commands.Choice[str],
    причина: str,
):
    async with get_session() as session:
        member = await crud.get_member_by_static(session, static)
        if member is None:
            await interaction.response.send_message(f"❌ Сотрудник со static `{static}` не найден.", ephemeral=True)
            return
        warning = await crud.issue_warning(
            session,
            member.id,
            level=WarningLevel[уровень.value],
            reason=причина,
            issued_by=str(interaction.user),
        )
        history = await crud.list_warnings(session, member.id)

    embed = discord.Embed(
        title=f"⚠️ Выговор: {member.full_name}",
        color=discord.Color.orange() if warning.level != WarningLevel.DEMOTION else discord.Color.red(),
    )
    embed.add_field(name="Уровень", value=warning.level.value, inline=True)
    embed.add_field(name="Кем выдан", value=warning.issued_by, inline=True)
    embed.add_field(name="Причина", value=причина, inline=False)
    embed.set_footer(text=f"Всего выговоров у сотрудника: {len(history)}")
    await interaction.response.send_message(embed=embed)


@warn_group.command(name="история", description="История выговоров сотрудника")
@app_commands.describe(static="Static ID сотрудника")
async def warn_history(interaction: discord.Interaction, static: str):
    async with get_session() as session:
        member = await crud.get_member_by_static(session, static)
        if member is None:
            await interaction.response.send_message(f"❌ Сотрудник со static `{static}` не найден.", ephemeral=True)
            return
        history = await crud.list_warnings(session, member.id)

    if not history:
        await interaction.response.send_message(f"У **{member.full_name}** нет выговоров.")
        return

    embed = discord.Embed(title=f"История выговоров: {member.full_name}", color=discord.Color.orange())
    for w in history[:20]:
        embed.add_field(
            name=f"{w.level.value} — {w.issued_at.strftime('%d.%m.%Y')}",
            value=f"{w.reason}\n_Выдал: {w.issued_by}_",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@warn_group.command(name="снять", description="Снять (удалить) выговор по ID")
@app_commands.describe(id="ID выговора")
@is_admin()
async def warn_remove(interaction: discord.Interaction, id: int):
    async with get_session() as session:
        ok = await crud.remove_warning(session, id)
    if not ok:
        await interaction.response.send_message("❌ Выговор с таким ID не найден.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Выговор снят.")


class WarningsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(warn_group)
    await bot.add_cog(WarningsCog(bot))
