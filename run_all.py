"""Единая точка входа для хостингов с одним сервисом: запускает Discord-бота
и веб-панель в ОДНОМ процессе, чтобы они использовали один и тот же файл базы
данных. Для локального запуска на компьютере по-прежнему используй
python -m bot.bot и python -m web.main отдельно — так удобнее для разработки.
"""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from bot.bot import bot
from core.config import DISCORD_TOKEN, WEB_HOST, WEB_PORT
from core.database import init_db
from web.main import app

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pai-crm")


async def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN не задан в переменных окружения")

    await init_db()

    config = uvicorn.Config(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
    server = uvicorn.Server(config)

    log.info("Запускаю бота и веб-панель в одном процессе...")
    await asyncio.gather(
        bot.start(DISCORD_TOKEN),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
