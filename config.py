"""
Central configuration – all settings are read from environment variables
(or a .env file loaded by python-dotenv).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip()]

# ─── RTMP ────────────────────────────────────────────────────────────────────
DEFAULT_RTMP_URL: str = os.getenv("DEFAULT_RTMP_URL", "rtmp://a.rtmp.youtube.com/live2")
DEFAULT_STREAM_KEY: str = os.getenv("DEFAULT_STREAM_KEY", "")

# ─── Google Drive ────────────────────────────────────────────────────────────
GDRIVE_CREDENTIALS_FILE: str = os.getenv("GDRIVE_CREDENTIALS_FILE", "credentials.json")

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage"))
DOWNLOADS_PATH = STORAGE_PATH / "downloads"
THUMBNAILS_PATH = STORAGE_PATH / "thumbnails"
LOGS_PATH = STORAGE_PATH / "logs"
DATABASE_PATH = STORAGE_PATH / "bot.db"

# Ensure directories exist at import time
for _p in (DOWNLOADS_PATH, THUMBNAILS_PATH, LOGS_PATH):
    _p.mkdir(parents=True, exist_ok=True)

FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH: str = os.getenv("FFPROBE_PATH", "ffprobe")

# ─── Database ────────────────────────────────────────────────────────────────
DATABASE_URL: str = f"sqlite+aiosqlite:///{DATABASE_PATH}"

# ─── Rate limiting ───────────────────────────────────────────────────────────
RATE_LIMIT_CALLS: int = int(os.getenv("RATE_LIMIT_CALLS", "5"))
RATE_LIMIT_PERIOD: int = int(os.getenv("RATE_LIMIT_PERIOD", "60"))

# ─── Streaming defaults ──────────────────────────────────────────────────────
DEFAULT_QUALITY: int = int(os.getenv("DEFAULT_QUALITY", "720"))
DEFAULT_VIDEO_BITRATE: str = os.getenv("DEFAULT_VIDEO_BITRATE", "2500k")
DEFAULT_AUDIO_BITRATE: str = os.getenv("DEFAULT_AUDIO_BITRATE", "128k")
DEFAULT_FPS: int = int(os.getenv("DEFAULT_FPS", "30"))

DEFAULT_BG_IMAGE: Path = Path(os.getenv("DEFAULT_BG_IMAGE", str(THUMBNAILS_PATH / "default_bg.jpg")))

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", str(LOGS_PATH / "bot.log"))

# ─── Quality map ─────────────────────────────────────────────────────────────
QUALITY_MAP = {
    480:  {"resolution": "854x480",  "vbitrate": "1500k", "fps": 30},
    720:  {"resolution": "1280x720", "vbitrate": "2500k", "fps": 30},
    1080: {"resolution": "1920x1080","vbitrate": "4500k", "fps": 30},
}
