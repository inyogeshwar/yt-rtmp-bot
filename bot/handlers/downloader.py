"""
yt-dlp download command handlers.

Commands:
  /yt url       – download best quality video
  /ytmp3 url    – download & convert to MP3
  /ytbest url   – download best + show info
  /ytinfo url   – show info only (no download)
"""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import db as _db
from bot.services import ytdlp_service as _yt
from bot.utils.helpers import human_duration, human_size

logger = logging.getLogger(__name__)
router = Router(name="downloader")


def _make_cb(status_msg):
    """Create a thread-safe progress callback that edits a Telegram message."""
    import asyncio
    loop = asyncio.get_event_loop()
    _last = {"text": ""}

    def cb(text: str):
        if text == _last["text"]:
            return
        _last["text"] = text
        asyncio.run_coroutine_threadsafe(
            _safe_edit(status_msg, text), loop
        )

    return cb


async def _safe_edit(msg, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass


@router.message(Command("yt"))
async def cmd_yt(message: Message, command: CommandObject) -> None:
    url = (command.args or "").strip()
    if not url:
        await message.answer("Usage: `/yt https://youtube.com/watch?v=...`", parse_mode="Markdown")
        return

    status = await message.answer("⬇️ Starting download…")
    cb     = _make_cb(status)

    try:
        paths = await _yt.download_best(url, progress_cb=cb)
    except Exception as exc:
        await status.edit_text(f"❌ Download failed: {exc}")
        return

    if not paths:
        await status.edit_text("❌ Download returned no files.")
        return

    path = paths[0]
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await status.edit_text(
        f"✅ Downloaded: `{path.name}`\nSize: {human_size(path.stat().st_size)}\n\n"
        f"Reply `live` to stream, or use /start\\_stream",
        parse_mode="Markdown",
    )


@router.message(Command("ytmp3"))
async def cmd_ytmp3(message: Message, command: CommandObject) -> None:
    url = (command.args or "").strip()
    if not url:
        await message.answer("Usage: `/ytmp3 https://youtube.com/watch?v=...`", parse_mode="Markdown")
        return

    status = await message.answer("⬇️ Downloading audio…")
    cb     = _make_cb(status)

    try:
        paths = await _yt.download_mp3(url, progress_cb=cb)
    except Exception as exc:
        await status.edit_text(f"❌ Download failed: {exc}")
        return

    if not paths:
        await status.edit_text("❌ No audio file produced.")
        return

    path = paths[0]
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await status.edit_text(
        f"✅ MP3 ready: `{path.name}`\nSize: {human_size(path.stat().st_size)}",
        parse_mode="Markdown",
    )
    try:
        await message.answer_audio(
            audio=path.open("rb"),
            title=path.stem,
            caption="🎵 Downloaded via yt-dlp",
        )
    except Exception:
        pass  # file may be too large for Telegram


@router.message(Command("ytbest"))
async def cmd_ytbest(message: Message, command: CommandObject) -> None:
    url = (command.args or "").strip()
    if not url:
        await message.answer("Usage: `/ytbest https://youtube.com/watch?v=...`", parse_mode="Markdown")
        return

    status = await message.answer("🔍 Fetching video info…")
    info   = await _yt.get_info(url)
    if not info:
        await status.edit_text("❌ Could not fetch info. Check the URL.")
        return

    await status.edit_text(
        f"📹 *{info.get('title', 'Unknown')}*\n"
        f"Channel : {info.get('uploader', '?')}\n"
        f"Duration: {human_duration(info.get('duration', 0))}\n"
        f"Views   : {info.get('view_count', 0):,}\n"
        f"Formats : {len(info.get('formats', []))}\n\n"
        f"⬇️ Starting best-quality download…",
        parse_mode="Markdown",
    )
    cb    = _make_cb(status)
    try:
        paths = await _yt.download_best(url, progress_cb=cb)
    except Exception as exc:
        await status.edit_text(f"❌ Download failed: {exc}")
        return

    if not paths:
        await status.edit_text("❌ Download returned no files.")
        return

    path = paths[0]
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await status.edit_text(
        f"✅ Downloaded: `{path.name}`\nSize: {human_size(path.stat().st_size)}",
        parse_mode="Markdown",
    )


@router.message(Command("ytinfo"))
async def cmd_ytinfo(message: Message, command: CommandObject) -> None:
    url = (command.args or "").strip()
    if not url:
        await message.answer("Usage: `/ytinfo https://youtube.com/watch?v=...`", parse_mode="Markdown")
        return
    status = await message.answer("🔍 Fetching info…")
    info   = await _yt.get_info(url)
    if not info:
        await status.edit_text("❌ Could not fetch info.")
        return

    # Build formats summary
    fmts = info.get("formats", [])
    fmt_lines = []
    seen = set()
    for f in reversed(fmts):
        h = f.get("height")
        ext = f.get("ext")
        key = (h, ext)
        if key in seen or not h:
            continue
        seen.add(key)
        vbr = f.get("vbr") or 0
        fmt_lines.append(f"  `{f['format_id']}` – {h}p {ext} ~{int(vbr)}kbps")
    fmt_summary = "\n".join(fmt_lines[:10]) or "  (none)"

    await status.edit_text(
        f"📹 *{info.get('title', '?')}*\n"
        f"Channel : {info.get('uploader', '?')}\n"
        f"Duration: {human_duration(info.get('duration', 0))}\n"
        f"Views   : {info.get('view_count', 0):,}\n\n"
        f"*Available formats (sample):*\n{fmt_summary}\n\n"
        f"Use `/yt {url}` to download.",
        parse_mode="Markdown",
    )


@router.message(Command("ytplaylist"))
async def cmd_ytplaylist(message: Message, command: CommandObject) -> None:
    url = (command.args or "").strip()
    if not url:
        await message.answer("Usage: `/ytplaylist https://youtube.com/playlist?list=...`", parse_mode="Markdown")
        return
    status = await message.answer("⬇️ Downloading playlist (this may take a while)…")
    cb     = _make_cb(status)
    try:
        paths = await _yt.download_playlist(url, progress_cb=cb)
    except Exception as exc:
        await status.edit_text(f"❌ Playlist download failed: {exc}")
        return
    await status.edit_text(
        f"✅ Downloaded {len(paths)} file(s) from playlist.\n"
        f"Use /list to see the queue.",
        parse_mode="Markdown",
    )
