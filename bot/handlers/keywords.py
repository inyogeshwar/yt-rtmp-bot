"""
Reply keyword parser.

When a user replies to a media message with a keyword, this handler triggers
the appropriate action without needing a slash command.

Supported keywords:
  live / stream       – start streaming the replied-to file
  mp3 / audio         – convert to MP3
  720 / 480 / 1080    – change quality and re-queue
  info / probe        – show FFprobe info
  thumbnail / thumb   – extract and send thumbnail
  loop                – toggle loop mode
  stop                – stop streaming
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message

from bot.database import db as _db
from bot.services import file_detector, ffmpeg_service as _ff
from bot.services.stream_manager import stream_manager
from bot.utils.helpers import human_duration, human_size
from config import DEFAULT_AUDIO_BITRATE, DEFAULT_QUALITY, DEFAULT_VIDEO_BITRATE

logger = logging.getLogger(__name__)
router = Router(name="keywords")

# Keyword → action map
QUALITY_RE = re.compile(r"^(480|720|1080)$")
LIVE_RE    = re.compile(r"^(live|stream|go live)$", re.IGNORECASE)
MP3_RE     = re.compile(r"^(mp3|audio|extract audio)$", re.IGNORECASE)
INFO_RE    = re.compile(r"^(info|probe|details)$", re.IGNORECASE)
THUMB_RE   = re.compile(r"^(thumbnail|thumb|screenshot)$", re.IGNORECASE)
LOOP_RE    = re.compile(r"^(loop|repeat)$", re.IGNORECASE)
STOP_RE    = re.compile(r"^(stop|halt|end stream)$", re.IGNORECASE)


@router.message(F.reply_to_message & F.text)
async def handle_keyword(message: Message, is_admin: bool = False) -> None:
    keyword = message.text.strip()
    uid     = message.from_user.id

    # Try to resolve file from replied message or last queued
    replied = message.reply_to_message
    file_path_str: str | None = None

    if replied:
        file_path_str = await _db.get_setting(f"last_file_{uid}")

    if not file_path_str:
        file_path_str = await _db.get_setting(f"last_file_{uid}")

    if not file_path_str or not Path(file_path_str).exists():
        # No file to act on – let other handlers process it
        return

    file_path = Path(file_path_str)

    # ── LIVE ─────────────────────────────────────────────────────────────────
    if LIVE_RE.match(keyword):
        if not is_admin:
            await message.answer("⛔ Only admins can start streams.")
            return
        rtmp_cfg = await _db.get_rtmp(uid)
        if not rtmp_cfg:
            await message.answer("⚠️ No RTMP config. Use /set\\_rtmp first.", parse_mode="Markdown")
            return

        quality  = int(await _db.get_setting(f"quality_{uid}", str(DEFAULT_QUALITY)))
        vbitrate = await _db.get_setting(f"vbitrate_{uid}", DEFAULT_VIDEO_BITRATE)
        loop     = (await _db.get_setting(f"loop_{uid}", "0")) == "1"

        # If file is audio-only, wrap with background image first
        try:
            info = await file_detector.probe(str(file_path))
        except Exception:
            info = None

        actual_path = str(file_path)
        if info and info.audio_only:
            status = await message.answer("⚙️ Wrapping audio with background image…")
            try:
                actual_path = str(await _ff.audio_to_video(str(file_path)))
                await status.edit_text("✅ Ready. Starting stream…")
            except Exception as exc:
                await status.edit_text(f"❌ Failed to prepare audio: {exc}")
                return
        elif info and info.video_only:
            await message.answer(
                "⚠️ Video has no audio track. Streaming anyway (silent)."
            )

        session_id = await _db.create_session(
            user_id=uid,
            rtmp_url=rtmp_cfg["rtmp_url"],
            stream_key=rtmp_cfg["stream_key"],
            quality=quality,
            vbitrate=vbitrate,
            abitrate=DEFAULT_AUDIO_BITRATE,
            loop_mode=loop,
            title=file_path.name,
        )

        bot = message.bot

        async def notify(user_id: int, text: str) -> None:
            try:
                await bot.send_message(user_id, text, parse_mode="Markdown")
            except Exception:
                pass

        try:
            await stream_manager.start(
                session_id=session_id,
                user_id=uid,
                input_path=actual_path,
                rtmp_url=rtmp_cfg["rtmp_url"],
                stream_key=rtmp_cfg["stream_key"],
                quality=quality,
                vbitrate=vbitrate,
                abitrate=DEFAULT_AUDIO_BITRATE,
                loop=loop,
                notify_cb=notify,
            )
            await message.answer(
                f"🟢 Stream started! Session: `{session_id[:8]}`\n"
                f"Quality: {quality}p  Loop: {'✅' if loop else '❌'}\n"
                f"Use `/stop_stream` to stop.",
                parse_mode="Markdown",
            )
        except Exception as exc:
            await message.answer(f"❌ Stream failed: {exc}")
        return

    # ── MP3 ──────────────────────────────────────────────────────────────────
    if MP3_RE.match(keyword):
        status = await message.answer("⚙️ Converting to MP3…")
        try:
            out = await _ff.convert_to_mp3(str(file_path))
            await status.edit_text(f"✅ `{out.name}`", parse_mode="Markdown")
            await message.answer_audio(audio=out.open("rb"), title=out.stem)
        except Exception as exc:
            await status.edit_text(f"❌ {exc}")
        return

    # ── QUALITY ───────────────────────────────────────────────────────────────
    m = QUALITY_RE.match(keyword)
    if m:
        q = int(m.group(1))
        await _db.set_setting(f"quality_{uid}", str(q))
        await message.answer(
            f"✅ Quality set to *{q}p*. Next stream will use this setting.",
            parse_mode="Markdown",
        )
        return

    # ── INFO ──────────────────────────────────────────────────────────────────
    if INFO_RE.match(keyword):
        try:
            info = await file_detector.probe(str(file_path))
            lines = [
                f"📊 *File Info*: `{file_path.name}`",
                f"Type     : {info.media_type}",
                f"Duration : {human_duration(info.duration)}",
                f"Size     : {human_size(info.size_bytes)}",
                f"Format   : {info.format_name}",
            ]
            if info.has_video:
                lines.append(f"Video    : {info.width}x{info.height} @ {info.fps:.1f}fps  ({info.video_codec})")
            if info.has_audio:
                lines.append(f"Audio    : {info.audio_codec}  {info.sample_rate}Hz  {info.channels}ch")
            await message.answer("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await message.answer(f"❌ Probe failed: {exc}")
        return

    # ── THUMBNAIL ─────────────────────────────────────────────────────────────
    if THUMB_RE.match(keyword):
        status = await message.answer("🖼️ Extracting thumbnail…")
        try:
            out = await _ff.extract_thumbnail(str(file_path))
            await status.delete()
            await message.answer_photo(photo=out.open("rb"), caption=f"🖼️ `{file_path.name}`", parse_mode="Markdown")
        except Exception as exc:
            await status.edit_text(f"❌ {exc}")
        return

    # ── LOOP ──────────────────────────────────────────────────────────────────
    if LOOP_RE.match(keyword):
        current = (await _db.get_setting(f"loop_{uid}", "0")) == "1"
        new_val = "0" if current else "1"
        await _db.set_setting(f"loop_{uid}", new_val)
        status = "✅ enabled" if new_val == "1" else "❌ disabled"
        await message.answer(f"🔁 Loop mode {status}.")
        return

    # ── STOP ──────────────────────────────────────────────────────────────────
    if STOP_RE.match(keyword):
        if not is_admin:
            await message.answer("⛔ Admin only.")
            return
        sessions = stream_manager.user_sessions(uid)
        if not sessions:
            await message.answer("ℹ️ No active streams.")
            return
        for sess in sessions:
            await stream_manager.stop(sess.session_id)
        await message.answer(f"🔴 Stopped {len(sessions)} stream(s).")
        return
