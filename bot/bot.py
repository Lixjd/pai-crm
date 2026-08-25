"""Точка входа Discord-бота отдела PAI.
Запуск: python -m bot.bot (из корня проекта)
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.config import DISCORD_GUILD_ID, DISCORD_TOKEN
from core.database import init_db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pai-bot")

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True

COGS = [
    "bot.cogs.roster",
    "bot.cogs.points_settings",
    "bot.cogs.reports",
    "bot.cogs.warnings",
    "bot.cogs.norms",
    "bot.cogs.events",
]


class PAIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)

    async def setup_hook(self) -> None:
        await init_db()
        for cog in COGS:
            await self.load_extension(cog)
            log.info("Загружен ког: %s", cog)

        if DISCORD_GUILD_ID:
            guild = discord.Object(id=DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
        else:
            synced = await self.tree.sync()
        log.info("Синхронизировано %d слэш-команд", len(synced))

    async def on_ready(self):
        log.info("Бот запущен как %s (ID: %s)", self.user, self.user.id)


bot = PAIBot()


def main():
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN не задан в .env")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
