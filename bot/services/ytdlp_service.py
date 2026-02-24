"""
yt-dlp download service wrapped in async helpers.

All heavy work runs in an executor so the event loop stays free.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yt_dlp  # type: ignore

from config import DOWNLOADS_PATH

logger = logging.getLogger(__name__)


# ─── Progress hook factory ────────────────────────────────────────────────────

def _make_progress_hook(callback: Optional[Callable] = None):
    """Return a yt-dlp progress hook that calls an async-safe callback."""
    # Capture the running event loop in the async context
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    def hook(d: dict):
        if callback is None:
            return
        if d["status"] == "downloading":
            pct = d.get("_percent_str", "?%").strip()
            speed = d.get("_speed_str", "?/s").strip()
            eta = d.get("_eta_str", "?").strip()
            loop.call_soon_threadsafe(
                callback, f"⬇️ {pct}  •  {speed}  •  ETA {eta}"
            )
        elif d["status"] == "finished":
            loop.call_soon_threadsafe(callback, "✅ Download finished, processing…")
    return hook


# ─── Core download helper ─────────────────────────────────────────────────────

async def _run_ytdlp(ydl_opts: dict, url: str) -> List[Dict]:
    """Execute yt-dlp in a thread pool, return list of info dicts."""
    loop = asyncio.get_running_loop()

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Normalise to list
            if info is None:
                return []
            entries = info.get("entries") or [info]
            return [ydl.sanitize_info(e) for e in entries if e]

    return await loop.run_in_executor(None, _download)


# ─── Public API ───────────────────────────────────────────────────────────────

async def download_best(
    url: str,
    progress_cb: Optional[Callable] = None,
) -> List[Path]:
    """Download best available quality."""
    opts = {
        "outtmpl": str(DOWNLOADS_PATH / "%(title)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "progress_hooks": [_make_progress_hook(progress_cb)],
        "quiet": True,
        "noplaylist": True,
    }
    infos = await _run_ytdlp(opts, url)
    return [Path(i["requested_downloads"][0]["filepath"]) for i in infos if "requested_downloads" in i]


async def download_mp3(
    url: str,
    progress_cb: Optional[Callable] = None,
) -> List[Path]:
    """Download and convert to MP3."""
    opts = {
        "outtmpl": str(DOWNLOADS_PATH / "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [_make_progress_hook(progress_cb)],
        "quiet": True,
        "noplaylist": True,
    }
    infos = await _run_ytdlp(opts, url)
    paths = []
    for i in infos:
        # post-processed path
        rds = i.get("requested_downloads", [{}])
        fp  = rds[0].get("filepath", "") if rds else ""
        if fp:
            # yt-dlp may rename to .mp3
            p = Path(fp)
            mp3_path = p.with_suffix(".mp3")
            if mp3_path.exists():
                paths.append(mp3_path)
            elif p.exists():
                paths.append(p)
    return paths


async def download_playlist(
    url: str,
    progress_cb: Optional[Callable] = None,
    fmt: str = "mp4",
) -> List[Path]:
    """Download an entire YouTube playlist."""
    opts = {
        "outtmpl": str(DOWNLOADS_PATH / "%(playlist_index)s - %(title)s.%(ext)s"),
        "format": f"bestvideo[ext={fmt}]+bestaudio[ext=m4a]/best[ext={fmt}]/best",
        "merge_output_format": fmt,
        "progress_hooks": [_make_progress_hook(progress_cb)],
        "quiet": True,
        "noplaylist": False,
        "ignoreerrors": True,
    }
    infos = await _run_ytdlp(opts, url)
    results = []
    for i in infos:
        rds = i.get("requested_downloads", [{}])
        fp  = rds[0].get("filepath", "") if rds else ""
        if fp and Path(fp).exists():
            results.append(Path(fp))
    return results


async def get_info(url: str) -> Optional[Dict]:
    """Fetch video metadata without downloading."""
    loop = asyncio.get_running_loop()
    opts = {"quiet": True, "noplaylist": True, "skip_download": True}

    def _fetch():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _fetch)
        return info
    except Exception as e:
        logger.error("yt-dlp info error: %s", e)
        return None


async def download_format(
    url: str,
    fmt_id: str,
    progress_cb: Optional[Callable] = None,
) -> Optional[Path]:
    """Download a specific yt-dlp format ID."""
    opts = {
        "outtmpl": str(DOWNLOADS_PATH / "%(title)s_%(format_id)s.%(ext)s"),
        "format": fmt_id,
        "progress_hooks": [_make_progress_hook(progress_cb)],
        "quiet": True,
        "noplaylist": True,
    }
    infos = await _run_ytdlp(opts, url)
    if infos:
        rds = infos[0].get("requested_downloads", [{}])
        fp  = rds[0].get("filepath", "") if rds else ""
        if fp and Path(fp).exists():
            return Path(fp)
    return None
