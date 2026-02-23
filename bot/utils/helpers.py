"""General helper utilities."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ─── URL helpers ─────────────────────────────────────────────────────────────

YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+"
)
GDRIVE_RE = re.compile(r"drive\.google\.com/(file/d/|open\?id=|uc\?)")
URL_RE    = re.compile(r"https?://\S+")


def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_RE.search(text))


def is_gdrive_url(text: str) -> bool:
    return bool(GDRIVE_RE.search(text))


def is_direct_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))


def extract_url(text: str) -> Optional[str]:
    m = URL_RE.search(text)
    return m.group(0) if m else None


def guess_ext_from_url(url: str) -> str:
    path = urlparse(url).path
    ext  = Path(path).suffix
    return ext if ext else ""


# ─── File helpers ─────────────────────────────────────────────────────────────

def is_video_ext(path: str | Path) -> bool:
    ext = Path(path).suffix.lower()
    return ext in {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v"}


def is_audio_ext(path: str | Path) -> bool:
    ext = Path(path).suffix.lower()
    return ext in {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus"}


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def human_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ─── Telegram helpers ─────────────────────────────────────────────────────────

def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


def split_text(text: str, max_len: int = 4096) -> list[str]:
    """Split a long string into Telegram-friendly chunks."""
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    parts.append(text)
    return parts
