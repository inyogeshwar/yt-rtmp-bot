"""
Stream control command handlers.

Commands:
  /start_stream   – start streaming the most recently queued file
  /stop_stream    – stop a stream session
  /pause_stream   – pause
  /resume_stream  – resume
  /status         – show all active sessions
  /sessions       – list user's sessions
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import db as _db
from bot.services.stream_manager import stream_manager
from config import DEFAULT_QUALITY, DEFAULT_VIDEO_BITRATE, DEFAULT_AUDIO_BITRATE

logger = logging.getLogger(__name__)
router = Router(name="stream")


async def _get_user_cfg(user_id: int):
    quality  = int(await _db.get_setting(f"quality_{user_id}", str(DEFAULT_QUALITY)))
    vbitrate = await _db.get_setting(f"vbitrate_{user_id}", DEFAULT_VIDEO_BITRATE)
    return quality, vbitrate


async def _notify_user(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text, parse_mode="Markdown")
    except Exception:
        pass


@router.message(Command("start_stream"))
async def cmd_start_stream(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return

    uid  = message.from_user.id
    args = (command.args or "").strip().split()

    # Resolve file: argument OR last queued file from DB setting
    file_path_str = args[0] if args else await _db.get_setting(f"last_file_{uid}")
    if not file_path_str:
        await message.answer(
            "⚠️ No file queued. Send a video/audio file first, or specify the path:\n"
            "`/start_stream path/to/file.mp4`",
            parse_mode="Markdown",
        )
        return

    # Security: Validate path is within STORAGE_PATH to prevent traversal
    from config import STORAGE_PATH
    try:
        candidate = Path(file_path_str).resolve()
        base      = STORAGE_PATH.resolve()
        if not candidate.is_relative_to(base) or not candidate.is_file():
            await message.answer("⛔ Invalid file path or access denied.")
            return
    except Exception:
        await message.answer("⚠️ Path resolution failed.")
        return

    file_path = candidate
    if not rtmp_cfg:
        await message.answer("⚠️ No RTMP config. Use /set\\_rtmp first.", parse_mode="Markdown")
        return

    quality, vbitrate = await _get_user_cfg(uid)
    loop = (await _db.get_setting(f"loop_{uid}", "0")) == "1"

    msg = await message.answer("🚀 Starting stream…")

    session_id = await _db.create_session(
        user_id=uid,
        rtmp_url=rtmp_cfg["rtmp_url"],
        stream_key=rtmp_cfg["stream_key"],
        quality=quality,
        vbitrate=vbitrate,
        abitrate=DEFAULT_AUDIO_BITRATE,
        loop_mode=loop,
        title=Path(file_path_str).name,
    )

    bot = message.bot

    async def notify(user_id: int, text: str) -> None:
        await _notify_user(bot, user_id, text)

    try:
        sess = await stream_manager.start(
            session_id=session_id,
            user_id=uid,
            input_path=file_path_str,
            rtmp_url=rtmp_cfg["rtmp_url"],
            stream_key=rtmp_cfg["stream_key"],
            quality=quality,
            vbitrate=vbitrate,
            abitrate=DEFAULT_AUDIO_BITRATE,
            loop=loop,
            notify_cb=notify,
        )
        await msg.edit_text(
            f"🟢 *Stream started!*\n"
            f"Session: `{session_id[:8]}…`\n"
            f"Quality: {quality}p  |  Bitrate: {vbitrate}\n"
            f"Loop: {'✅' if loop else '❌'}\n\n"
            f"Use `/stop_stream {session_id[:8]}` to stop.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("Stream start failed")
        await msg.edit_text(f"❌ Failed to start stream: {exc}")


@router.message(Command("stop_stream"))
async def cmd_stop_stream(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    uid      = message.from_user.id
    args     = (command.args or "").strip()
    sessions = stream_manager.user_sessions(uid)

    if not sessions and not args:
        await message.answer("ℹ️ No active sessions.")
        return

    # Find by partial ID or stop all
    if args:
        target = next((s for s in sessions if s.session_id.startswith(args)), None)
        if not target:
            await message.answer(f"❌ Session `{args}` not found.", parse_mode="Markdown")
            return
        stopped = await stream_manager.stop(target.session_id)
        await message.answer(
            f"{'🔴 Stopped' if stopped else '⚠️ Could not stop'} session `{target.session_id[:8]}`.",
            parse_mode="Markdown",
        )
    else:
        # Stop all user sessions
        count = 0
        for sess in sessions:
            if await stream_manager.stop(sess.session_id):
                count += 1
        await message.answer(f"🔴 Stopped {count} session(s).")


@router.message(Command("pause_stream"))
async def cmd_pause_stream(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    args     = (command.args or "").strip()
    uid      = message.from_user.id
    sessions = stream_manager.user_sessions(uid)
    target   = next((s for s in sessions if s.session_id.startswith(args)), sessions[0] if sessions else None)
    if not target:
        await message.answer("⚠️ No active session found.")
        return
    ok = await stream_manager.pause(target.session_id)
    await message.answer(
        f"{'⏸️ Paused' if ok else '⚠️ Could not pause'} `{target.session_id[:8]}`.",
        parse_mode="Markdown",
    )


@router.message(Command("resume_stream"))
async def cmd_resume_stream(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    args     = (command.args or "").strip()
    uid      = message.from_user.id
    sessions = stream_manager.user_sessions(uid)
    target   = next((s for s in sessions if s.session_id.startswith(args)), sessions[0] if sessions else None)
    if not target:
        await message.answer("⚠️ No paused session found.")
        return
    ok = await stream_manager.resume(target.session_id)
    await message.answer(
        f"{'▶️ Resumed' if ok else '⚠️ Could not resume'} `{target.session_id[:8]}`.",
        parse_mode="Markdown",
    )


@router.message(Command("status"))
async def cmd_status(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    all_sess = stream_manager.all_sessions()
    if not all_sess:
        await message.answer("📭 No active streams.")
        return
    lines = [f"📺 *Active Streams ({len(all_sess)})*\n"]
    for s in all_sess:
        emoji = {"running": "🟢", "paused": "⏸️"}.get(s.status, "⚪")
        lines.append(
            f"{emoji} `{s.session_id[:8]}` – {s.status} – {s.quality}p – user `{s.user_id}`"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("sessions"))
async def cmd_sessions(message: Message) -> None:
    uid  = message.from_user.id
    rows = await _db.get_user_sessions(uid)
    if not rows:
        await message.answer("📭 No sessions found.")
        return
    lines = [f"📋 *Your Sessions ({len(rows)})*\n"]
    for r in rows[-10:]:
        emoji = {"running": "🟢", "stopped": "🔴", "paused": "⏸️", "crashed": "💥"}.get(r["status"], "⚪")
        lines.append(f"{emoji} `{r['id'][:8]}` – {r['status']} – {r['quality']}p – {r['title'] or 'untitled'}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("loop"))
async def cmd_loop(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    uid     = message.from_user.id
    current = (await _db.get_setting(f"loop_{uid}", "0")) == "1"
    new_val = "0" if current else "1"
    await _db.set_setting(f"loop_{uid}", new_val)
    status = "✅ enabled" if new_val == "1" else "❌ disabled"
    await message.answer(f"🔁 Loop mode {status}.")
