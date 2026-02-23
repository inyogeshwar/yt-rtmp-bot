"""
Playlist management command handlers.

Commands:
  /add [file_path]   – add current or specified file to active session playlist
  /remove id         – remove playlist item by ID
  /list              – show playlist
  /clear             – clear playlist
  /playlist_stream   – start streaming the full playlist
"""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import db as _db
from bot.services import file_detector
from bot.services.stream_manager import stream_manager
from config import DEFAULT_AUDIO_BITRATE, DEFAULT_QUALITY, DEFAULT_VIDEO_BITRATE

logger = logging.getLogger(__name__)
router = Router(name="playlist")


async def _get_active_session_id(user_id: int) -> str | None:
    """Return the latest running session for a user, or create a placeholder."""
    sessions = stream_manager.user_sessions(user_id)
    if sessions:
        return sessions[0].session_id
    # Fall back to DB (last created session that is not stopped)
    db_sessions = await _db.get_user_sessions(user_id, active_only=False)
    for s in reversed(db_sessions):
        if s["status"] not in ("stopped", "crashed"):
            return s["id"]
    return None


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject) -> None:
    uid  = message.from_user.id
    args = (command.args or "").strip()

    file_path = args or await _db.get_setting(f"last_file_{uid}")
    if not file_path or not Path(file_path).exists():
        await message.answer("⚠️ No file to add. Send a file first or specify path.")
        return

    session_id = await _get_active_session_id(uid)
    if not session_id:
        # Auto-create a session shell in DB (not streaming yet)
        rtmp_cfg = await _db.get_rtmp(uid)
        if not rtmp_cfg:
            await message.answer("⚠️ No RTMP config. Use /set\\_rtmp first.", parse_mode="Markdown")
            return
        quality = int(await _db.get_setting(f"quality_{uid}", str(DEFAULT_QUALITY)))
        vbitrate = await _db.get_setting(f"vbitrate_{uid}", DEFAULT_VIDEO_BITRATE)
        session_id = await _db.create_session(
            user_id=uid,
            rtmp_url=rtmp_cfg["rtmp_url"],
            stream_key=rtmp_cfg["stream_key"],
            quality=quality,
            vbitrate=vbitrate,
            abitrate=DEFAULT_AUDIO_BITRATE,
        )

    # Probe duration
    title = Path(file_path).name
    duration = 0.0
    try:
        info = await file_detector.probe(file_path)
        duration = info.duration
    except Exception:
        pass

    item_id = await _db.playlist_add(session_id, file_path, title, duration)
    items   = await _db.playlist_list(session_id)
    await message.answer(
        f"✅ Added to playlist (item #{item_id})\n"
        f"📋 Queue: {len(items)} item(s)\nSession: `{session_id[:8]}`",
        parse_mode="Markdown",
    )


@router.message(Command("remove"))
async def cmd_remove(message: Message, command: CommandObject) -> None:
    args = (command.args or "").strip()
    if not args.isdigit():
        await message.answer("Usage: `/remove item_id`", parse_mode="Markdown")
        return
    await _db.playlist_remove(int(args))
    await message.answer(f"🗑️ Item `{args}` removed.", parse_mode="Markdown")


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    uid = message.from_user.id
    session_id = await _get_active_session_id(uid)
    if not session_id:
        await message.answer("📭 No active session. Use /add to create one.")
        return

    items = await _db.playlist_list(session_id)
    if not items:
        await message.answer(f"📭 Playlist is empty for session `{session_id[:8]}`.", parse_mode="Markdown")
        return

    lines = [f"📋 *Playlist* (session `{session_id[:8]}`)\n"]
    for it in items:
        status_icon = "✅" if it["played"] else "⏳"
        dur = f"{int(it['duration']//60)}:{int(it['duration']%60):02d}" if it["duration"] else "?"
        lines.append(f"{status_icon} `{it['id']}` – {it['title'] or 'untitled'} [{dur}]")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("clear"))
async def cmd_clear(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    uid = message.from_user.id
    session_id = await _get_active_session_id(uid)
    if not session_id:
        await message.answer("📭 No active session.")
        return
    await _db.playlist_clear(session_id)
    await message.answer("🗑️ Playlist cleared.")


@router.message(Command("playlist_stream"))
async def cmd_playlist_stream(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return

    uid = message.from_user.id
    session_id = await _get_active_session_id(uid)
    if not session_id:
        await message.answer("⚠️ No session found. Use /add to build a playlist first.")
        return

    items = await _db.playlist_list(session_id)
    unplayed = [it for it in items if not it["played"]]
    if not unplayed:
        await message.answer("⚠️ Playlist is empty or all items already played.")
        return

    rtmp_cfg = await _db.get_rtmp(uid)
    if not rtmp_cfg:
        await message.answer("⚠️ No RTMP config. Use /set\\_rtmp first.", parse_mode="Markdown")
        return

    from bot.services import ffmpeg_service as _ff
    quality  = int(await _db.get_setting(f"quality_{uid}", str(DEFAULT_QUALITY)))
    vbitrate = await _db.get_setting(f"vbitrate_{uid}", DEFAULT_VIDEO_BITRATE)
    loop     = (await _db.get_setting(f"loop_{uid}", "0")) == "1"
    paths    = [it["file_path"] for it in unplayed]

    status = await message.answer(f"🚀 Starting playlist stream ({len(paths)} items)…")

    bot = message.bot

    async def notify(user_id: int, text: str) -> None:
        try:
            await bot.send_message(user_id, text, parse_mode="Markdown")
        except Exception:
            pass

    try:
        from bot.services.ffmpeg_service import start_playlist_stream
        proc = await start_playlist_stream(
            playlist=paths,
            rtmp_url=rtmp_cfg["rtmp_url"],
            stream_key=rtmp_cfg["stream_key"],
            quality=quality,
            vbitrate=vbitrate,
            loop=loop,
        )
        # Store process in stream_manager manually
        from bot.services.stream_manager import Session
        sess = Session(
            session_id=session_id,
            user_id=uid,
            process=proc,
            input_path=paths[0],
            rtmp_url=rtmp_cfg["rtmp_url"],
            stream_key=rtmp_cfg["stream_key"],
            quality=quality,
            vbitrate=vbitrate,
            abitrate=DEFAULT_AUDIO_BITRATE,
            loop=loop,
            notify_cb=notify,
        )
        stream_manager._sessions[session_id] = sess
        await _db.update_session_status(session_id, "running")
        import asyncio
        sess._monitor_task = asyncio.create_task(stream_manager._monitor(sess))

        await status.edit_text(
            f"🟢 *Playlist stream started!*\n"
            f"Session: `{session_id[:8]}…`\n"
            f"Items  : {len(paths)}\n"
            f"Loop   : {'✅' if loop else '❌'}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        await status.edit_text(f"❌ Failed: {exc}")
