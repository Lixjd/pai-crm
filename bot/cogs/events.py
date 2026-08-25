"""События/собрания с отметкой присутствия (п.6)."""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import is_admin
from core import crud
from core.database import get_session

event_group = app_commands.Group(name="событие", description="Собрания и мероприятия отдела")


@event_group.command(name="создать", description="Создать событие/собрание")
@app_commands.describe(
    название="Название события",
    дата="Дата и время в формате ДД.ММ.ГГГГ ЧЧ:ММ",
    описание="Описание (необязательно)",
)
@is_admin()
async def event_create(interaction: discord.Interaction, название: str, дата: str, описание: str = ""):
    try:
        when = dt.datetime.strptime(дата, "%d.%m.%Y %H:%M")
    except ValueError:
        await interaction.response.send_message(
            "❌ Неверный формат даты. Используй ДД.ММ.ГГГГ ЧЧ:ММ, например 30.08.2026 19:00", ephemeral=True
        )
        return

    async with get_session() as session:
        event = await crud.create_event(
            session, title=название, event_datetime=when, description=описание, created_by=str(interaction.user)
        )

    await interaction.response.send_message(
        f"✅ Событие **{event.title}** создано на {when.strftime('%d.%m.%Y %H:%M')}. "
        f"ID события: `{event.id}`. Весь текущий состав приглашён — отмечайте присутствие через "
        f"/событие отметить."
    )


@event_group.command(name="список", description="Список событий")
@app_commands.describe(только_будущие="Показать только предстоящие события")
async def event_list(interaction: discord.Interaction, только_будущие: bool = True):
    async with get_session() as session:
        events = await crud.list_events(session, upcoming_only=только_будущие)

    if not events:
        await interaction.response.send_message("Событий нет.")
        return

    embed = discord.Embed(title="События отдела", color=discord.Color.purple())
    for e in events[:15]:
        embed.add_field(
            name=f"#{e.id} — {e.title}",
            value=f"{e.event_datetime.strftime('%d.%m.%Y %H:%M')}" + (f"\n{e.description}" if e.description else ""),
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@event_group.command(name="отметить", description="Отметить присутствие сотрудника на событии")
@app_commands.describe(id_события="ID события", static="Static ID сотрудника", присутствовал="Присутствовал ли на событии")
@is_admin()
async def event_mark(interaction: discord.Interaction, id_события: int, static: str, присутствовал: bool):
    async with get_session() as session:
        member = await crud.get_member_by_static(session, static)
        if member is None:
            await interaction.response.send_message(f"❌ Сотрудник со static `{static}` не найден.", ephemeral=True)
            return
        event = await crud.get_event(session, id_события)
        if event is None:
            await interaction.response.send_message(f"❌ Событие с ID `{id_события}` не найдено.", ephemeral=True)
            return
        await crud.mark_attendance(session, id_события, member.id, присутствовал)

    mark = "присутствовал ✅" if присутствовал else "отсутствовал ❌"
    await interaction.response.send_message(f"Отмечено: **{member.full_name}** — {mark} на «{event.title}».")


@event_group.command(name="посещаемость", description="Показать посещаемость по событию")
@app_commands.describe(id_события="ID события")
async def event_attendance(interaction: discord.Interaction, id_события: int):
    async with get_session() as session:
        event = await crud.get_event(session, id_события)

    if event is None:
        await interaction.response.send_message(f"❌ Событие с ID `{id_события}` не найдено.", ephemeral=True)
        return

    present = [a for a in event.attendances if a.present is True]
    absent = [a for a in event.attendances if a.present is False]
    unmarked = [a for a in event.attendances if a.present is None]

    embed = discord.Embed(
        title=f"Посещаемость: {event.title}",
        description=f"{event.event_datetime.strftime('%d.%m.%Y %H:%M')}",
        color=discord.Color.purple(),
    )
    embed.add_field(name=f"✅ Присутствовали ({len(present)})", value="\n".join(f"• {a.member.full_name}" for a in present) or "—", inline=False)
    embed.add_field(name=f"❌ Отсутствовали ({len(absent)})", value="\n".join(f"• {a.member.full_name}" for a in absent) or "—", inline=False)
    if unmarked:
        embed.add_field(name=f"⏳ Не отмечены ({len(unmarked)})", value="\n".join(f"• {a.member.full_name}" for a in unmarked) or "—", inline=False)

    await interaction.response.send_message(embed=embed)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    bot.tree.add_command(event_group)
    await bot.add_cog(EventsCog(bot))
