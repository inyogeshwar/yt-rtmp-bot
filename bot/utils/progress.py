"""
Telegram upload/download progress bar helper.

Usage:
    tracker = ProgressTracker(message, prefix="Uploading")
    await bot.download(file, destination=path, progress=tracker.hook)
"""
from __future__ import annotations

import time
from typing import Optional

from aiogram.types import Message


class ProgressTracker:
    MIN_UPDATE_INTERVAL = 3.0  # seconds between Telegram edits

    def __init__(self, message: Message, prefix: str = "Downloading") -> None:
        self._msg       = message
        self._prefix    = prefix
        self._last_edit = 0.0
        self._last_pct  = -1

    async def hook(self, current: int, total: int) -> None:
        """Pass this to aiogram download/upload progress callbacks."""
        if not total:
            return
        pct  = int(current / total * 100)
        now  = time.monotonic()
        if pct == self._last_pct and now - self._last_edit < self.MIN_UPDATE_INTERVAL:
            return
        self._last_pct  = pct
        self._last_edit = now
        bar = _build_bar(pct)
        size_str = _human(current) + " / " + _human(total)
        text = f"{self._prefix}\n{bar} {pct}%\n{size_str}"
        try:
            await self._msg.edit_text(text)
        except Exception:
            pass  # ignore rate-limit or already deleted

    async def done(self, text: str = "✅ Done.") -> None:
        try:
            await self._msg.edit_text(text)
        except Exception:
            pass


def _build_bar(pct: int, width: int = 20) -> str:
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} TB"
