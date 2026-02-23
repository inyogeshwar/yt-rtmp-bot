"""
Token-bucket rate limiting middleware.

Each user gets at most RATE_LIMIT_CALLS messages per RATE_LIMIT_PERIOD seconds.
Admins are exempt.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable, Deque, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from config import RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self._buckets: Dict[int, Deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        is_admin = data.get("is_admin", False)
        if is_admin:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        uid    = user.id
        now    = time.monotonic()
        bucket = self._buckets[uid]

        # Remove timestamps outside the window
        while bucket and bucket[0] < now - RATE_LIMIT_PERIOD:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT_CALLS:
            retry_in = int(RATE_LIMIT_PERIOD - (now - bucket[0]))
            if isinstance(event, Message):
                try:
                    await event.answer(
                        f"⏳ Slow down! You can send {RATE_LIMIT_CALLS} commands "
                        f"per {RATE_LIMIT_PERIOD}s. Retry in {retry_in}s."
                    )
                except Exception:
                    pass
            return  # drop the event

        bucket.append(now)
        return await handler(event, data)
