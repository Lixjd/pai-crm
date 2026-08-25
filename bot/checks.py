"""Проверка прав: кто может пользоваться админ-командами бота
(добавление в состав, выговоры, настройки баллов и т.д.)."""
from __future__ import annotations

import discord
from discord import app_commands

from core.config import ADMIN_ROLE_IDS


def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if not ADMIN_ROLE_IDS:
            # Если роли не настроены - пускаем всех, чтобы бот не был бесполезен
            # сразу после установки. Настоятельно рекомендуется задать ADMIN_ROLE_IDS.
            return True
        user_role_ids = {r.id for r in getattr(interaction.user, "roles", [])}
        return bool(user_role_ids & ADMIN_ROLE_IDS)

    return app_commands.check(predicate)
