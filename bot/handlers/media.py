"""
Media input handler.

Handles:
- Telegram file uploads (video, audio, document)
- Direct URL input
- Google Drive links
- Auto file type detection via FFprobe
- FFmpeg processing commands (/convert_mp4, /extract_audio, /thumbnail)
"""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, Video, Audio, Document, Voice

from bot.database import db as _db
from bot.services import file_detector, ffmpeg_service as _ff
from bot.services.gdrive_service import download_gdrive
from bot.utils.helpers import (
    is_youtube_url, is_gdrive_url, is_direct_url,
    is_video_ext, is_audio_ext, human_size, human_duration,
)
from bot.utils.progress import ProgressTracker
from config import DOWNLOADS_PATH

logger = logging.getLogger(__name__)
router = Router(name="media")


# ─── File upload handlers ─────────────────────────────────────────────────────

async def _save_telegram_file(message: Message, file_id: str, filename: str) -> Path:
    """Download a Telegram file with a progress bar."""
    DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS_PATH / filename
    status_msg = await message.answer(f"⬇️ Downloading `{filename}`…", parse_mode="Markdown")
    tracker = ProgressTracker(status_msg, prefix=f"⬇️ `{filename}`")
    bot = message.bot
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, destination=str(dest), progress=tracker.hook)
    await tracker.done(f"✅ Saved: `{filename}`")
    return dest


async def _probe_and_reply(message: Message, path: Path) -> file_detector.MediaInfo:
    """Run FFprobe and send a summary."""
    try:
        info = await file_detector.probe(path)
    except Exception as exc:
        await message.answer(f"⚠️ Could not probe file: {exc}")
        raise

    lines = [
        f"📊 *File Info*: `{path.name}`",
        f"Type    : {info.media_type}",
        f"Duration: {human_duration(info.duration)}",
        f"Size    : {human_size(info.size_bytes)}",
        f"Format  : {info.format_name}",
    ]
    if info.has_video:
        fps_str = f" @ {info.fps:.1f}fps" if info.fps is not None else ""
        lines.append(f"Video   : {info.width}x{info.height}{fps_str}  ({info.video_codec})")
    if info.has_audio:
        lines.append(f"Audio   : {info.audio_codec}  {info.sample_rate}Hz  {info.channels}ch")
    if info.video_only:
        lines.append("⚠️ No audio track found! Reply `live` anyway or add audio first.")
    await message.answer("\n".join(lines), parse_mode="Markdown")
    return info


@router.message(F.video)
async def handle_video(message: Message) -> None:
    v: Video = message.video
    filename = v.file_name or f"video_{v.file_id[-8:]}.mp4"
    path = await _save_telegram_file(message, v.file_id, filename)
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await _probe_and_reply(message, path)
    await message.answer(
        "💡 Reply keywords: `live` | `mp3` | `720` | `480` | `1080` | `info` | `thumbnail`",
        parse_mode="Markdown",
    )


@router.message(F.audio)
async def handle_audio(message: Message) -> None:
    a: Audio = message.audio
    filename = a.file_name or f"audio_{a.file_id[-8:]}.mp3"
    path = await _save_telegram_file(message, a.file_id, filename)
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await message.answer(
        f"🎵 Audio saved: `{filename}`\n"
        f"Duration: {human_duration(a.duration)}\n"
        f"💡 Reply `live` to stream with background image, or `mp3` to convert.",
        parse_mode="Markdown",
    )


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    v: Voice = message.voice
    filename = f"voice_{v.file_id[-8:]}.ogg"
    path = await _save_telegram_file(message, v.file_id, filename)
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))
    await message.answer(f"🎙️ Voice note saved: `{filename}`", parse_mode="Markdown")


@router.message(F.document)
async def handle_document(message: Message) -> None:
    doc: Document = message.document
    filename = doc.file_name or f"doc_{doc.file_id[-8:]}"
    path = await _save_telegram_file(message, doc.file_id, filename)
    await _db.set_setting(f"last_file_{message.from_user.id}", str(path))

    if is_video_ext(filename) or is_audio_ext(filename):
        await _probe_and_reply(message, path)
        await message.answer(
            "💡 Reply keywords: `live` | `mp3` | `720` | `info` | `thumbnail`",
            parse_mode="Markdown",
        )
    else:
        await message.answer(f"📄 File saved: `{filename}`", parse_mode="Markdown")


# ─── URL inputs ───────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"https?://\S+"))
async def handle_url(message: Message) -> None:
    url = message.text.strip()
    uid = message.from_user.id

    if is_youtube_url(url):
        await message.answer(
            "🎬 YouTube URL detected!\n"
            "Use:\n"
            "• `/yt <url>` – best quality download\n"
            "• `/ytmp3 <url>` – MP3 audio\n"
            "• `/ytbest <url>` – best + info",
            parse_mode="Markdown",
        )
        return

    if is_gdrive_url(url):
        status = await message.answer("⬇️ Downloading from Google Drive…")
        path = await download_gdrive(url)
        if not path:
            await status.edit_text("❌ Google Drive download failed. Ensure the file is public.")
            return
        await _db.set_setting(f"last_file_{uid}", str(path))
        await status.edit_text(f"✅ Downloaded: `{path.name}`", parse_mode="Markdown")
        if is_video_ext(path) or is_audio_ext(path):
            await _probe_and_reply(message, path)
        return

    if is_direct_url(url):
        status = await message.answer("⬇️ Downloading from URL…")
        import aiohttp
        import time
        try:
            filename = Path(url.split("?")[0]).name or "download"
            DOWNLOADS_PATH.mkdir(parents=True, exist_ok=True)
            dest = DOWNLOADS_PATH / filename
            timeout = aiohttp.ClientTimeout(total=3600, connect=30, sock_read=300)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status >= 400:
                        await status.edit_text(f"❌ Download failed: HTTP {resp.status}")
                        return
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_pct = -1
                    last_edit = 0
                    with open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 512):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = int(downloaded / total * 100)
                                now = time.monotonic()
                                if pct != last_pct and (pct // 20 != last_pct // 20 or now - last_edit > 5):
                                    try:
                                        await status.edit_text(f"⬇️ {pct}%…")
                                        last_pct = pct
                                        last_edit = now
                                    except Exception:
                                        pass
            await _db.set_setting(f"last_file_{uid}", str(dest))
            await status.edit_text(f"✅ Downloaded: `{dest.name}`", parse_mode="Markdown")
            if is_video_ext(dest) or is_audio_ext(dest):
                await _probe_and_reply(message, dest)
        except Exception as exc:
            await status.edit_text(f"❌ Download failed: {exc}")


# ─── FFmpeg processing commands ───────────────────────────────────────────────

@router.message(Command("convert_mp4"))
async def cmd_convert_mp4(message: Message, _command: CommandObject) -> None:
    uid = message.from_user.id
    src = await _db.get_setting(f"last_file_{uid}")
    if not src or not Path(src).exists():
        await message.answer("⚠️ No file queued. Send a video first.")
        return
    quality = int(await _db.get_setting(f"quality_{uid}", "720"))
    status  = await message.answer(f"⚙️ Converting to {quality}p MP4…")
    try:
        out = await _ff.convert_to_mp4(src, quality=quality)
        await _db.set_setting(f"last_file_{uid}", str(out))
        await status.edit_text(f"✅ Converted: `{out.name}`", parse_mode="Markdown")
    except Exception as exc:
        await status.edit_text(f"❌ Conversion failed: {exc}")


@router.message(Command("extract_audio"))
async def cmd_extract_audio(message: Message) -> None:
    uid = message.from_user.id
    src = await _db.get_setting(f"last_file_{uid}")
    if not src or not Path(src).exists():
        await message.answer("⚠️ No file queued. Send a video first.")
        return
    status = await message.answer("⚙️ Extracting audio…")
    try:
        out = await _ff.convert_to_mp3(src)
        await status.edit_text(f"✅ Audio extracted: `{out.name}`", parse_mode="Markdown")
        await message.answer_audio(
            audio=out.open("rb"),
            caption="🎵 Extracted audio",
        )
    except Exception as exc:
        await status.edit_text(f"❌ Extraction failed: {exc}")


@router.message(Command("thumbnail"))
async def cmd_thumbnail(message: Message) -> None:
    uid = message.from_user.id
    src = await _db.get_setting(f"last_file_{uid}")
    if not src or not Path(src).exists():
        await message.answer("⚠️ No file queued. Send a video first.")
        return
    status = await message.answer("🖼️ Extracting thumbnail…")
    try:
        out = await _ff.extract_thumbnail(src)
        await status.delete()
        await message.answer_photo(
            photo=out.open("rb"),
            caption=f"🖼️ Thumbnail from `{Path(src).name}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await status.edit_text(f"❌ Failed: {exc}")


@router.message(Command("probe"))
async def cmd_probe(message: Message) -> None:
    uid = message.from_user.id
    src = await _db.get_setting(f"last_file_{uid}")
    if not src or not Path(src).exists():
        await message.answer("⚠️ No file queued.")
        return
    await _probe_and_reply(message, Path(src))
