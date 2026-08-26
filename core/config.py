"""Общая конфигурация проекта: читается из .env одним и тем же способом
и для бота, и для веб-панели, чтобы обе части всегда смотрели в одну БД."""
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or 0)
ADMIN_ROLE_IDS = {
    int(x) for x in os.getenv("ADMIN_ROLE_IDS", "").split(",") if x.strip().isdigit()
}

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./pai_crm.db")

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
# Railway сам назначает порт через переменную PORT — используем её, если она есть
WEB_PORT = int(os.getenv("PORT") or os.getenv("WEB_PORT", "8000"))
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "change_me")
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "change_me_too")
