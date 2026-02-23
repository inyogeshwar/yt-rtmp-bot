"""
Authentication middleware.

- Auto-upserts user in the database.
- Attaches `is_admin` flag to handler data.
- Rejects banned users.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.database import db as _db
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        # Upsert into DB
        await _db.upsert_user(
            user_id=user.id,
            username=user.username or "",
            full_name=user.full_name,
        )

        # Attach convenient flags
        db_user = await _db.get_user(user.id)
        role = db_user["role"] if db_user else "user"

        if role == "banned":
            logger.info("Banned user %s tried to use bot", user.id)
            return  # silently ignore

        data["is_admin"]  = (user.id in ADMIN_IDS) or (role == "admin")
        data["user_role"] = role
        return await handler(event, data)
