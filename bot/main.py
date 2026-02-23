"""
Bot initialisation and startup.

Creates the Bot + Dispatcher, registers all routers and middlewares,
initialises the database, then starts polling.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from bot.database.db import init_db, close_db
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.handlers import admin, media, stream, downloader, playlist, keywords
from bot.utils.helpers import human_size

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = Path(config.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )
    # Silence noisy libraries
    for noisy in ("aiohttp", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def on_startup(bot: Bot) -> None:
    await init_db()
    me = await bot.get_me()
    logger.info("Bot started: @%s  (id=%s)", me.username, me.id)

    # Notify all admins
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🟢 *Bot online!*\n@{me.username} is ready.",
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def on_shutdown(bot: Bot) -> None:
    await close_db()
    logger.info("Bot shutdown.")
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🔴 Bot is shutting down.", parse_mode="Markdown")
        except Exception:
            pass


def create_bot() -> Bot:
    return Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # ── Middlewares ────────────────────────────────────────────────────────
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(RateLimitMiddleware())

    # ── Routers ────────────────────────────────────────────────────────────
    # Order matters: more specific routes first
    dp.include_router(admin.router)
    dp.include_router(stream.router)
    dp.include_router(downloader.router)
    dp.include_router(playlist.router)
    dp.include_router(media.router)      # catches file uploads & URLs
    dp.include_router(keywords.router)   # fallback reply keyword parser

    return dp


async def main() -> None:
    setup_logging()

    bot = create_bot()
    dp  = create_dispatcher()

    dp.startup.register(lambda: on_startup(bot))
    dp.shutdown.register(lambda: on_shutdown(bot))

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(dp.stop_polling()))
        except NotImplementedError:
            pass  # Windows

    logger.info("Starting polling…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
