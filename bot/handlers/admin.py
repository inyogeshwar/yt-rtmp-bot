"""
Admin command handlers.

Commands:
  /start         – welcome
  /help          – full command list
  /set_rtmp      – configure RTMP URL + stream key
  /set_rtmp_key  – update stream key only
  /show_rtmp     – display current RTMP config
  /quality       – set default stream quality
  /bitrate       – set default video bitrate
  /ban           – ban a user
  /unban         – unban a user
  /promote       – promote user to admin
  /broadcast     – send message to all users
  /logs          – show recent DB logs
  /stats         – show usage stats
"""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import db as _db
from bot.utils.security import mask_key
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router(name="admin")

HELP_TEXT = """
📡 *Advanced Media Streaming Bot*

─── 🔐 Admin Commands ───
/set\\_rtmp `rtmp_url stream_key` – set RTMP destination
/set\\_rtmp\\_key `key` – update stream key only
/show\\_rtmp – view current RTMP config
/quality `480|720|1080` – set stream quality
/bitrate `2500k` – set video bitrate
/ban `user_id` – ban user
/unban `user_id` – unban user
/promote `user_id` – make user admin
/broadcast `message` – message all users
/stats – usage statistics
/logs – recent bot logs

─── 📺 Stream Commands ───
/start\\_stream – start streaming (uses queued file)
/stop\\_stream – stop active stream
/pause\\_stream `session_id` – pause stream
/resume\\_stream `session_id` – resume stream
/status – all active streams
/sessions – your stream sessions

─── 📥 Download Commands ───
/yt `url` – download best quality
/ytmp3 `url` – download as MP3
/ytbest `url` – download best + info
/ytinfo `url` – show video info only

─── 🎵 Playlist Commands ───
/add `file_path` – add to playlist
/remove `id` – remove item
/list – show playlist
/clear – clear playlist

─── ⚙️ Processing Commands ───
/convert\\_mp4 – convert last file to MP4
/extract\\_audio – extract audio from last file
/thumbnail – extract thumbnail
/loop – toggle loop mode

─── 📌 Reply Keywords ───
Reply to a file with:
• `live` – stream the file
• `mp3` – convert to MP3
• `720` / `480` / `1080` – change quality
• `info` – probe file info
• `thumbnail` – extract thumbnail
"""


@router.message(Command("start"))
async def cmd_start(message: Message, is_admin: bool = False) -> None:
    role = "👑 Admin" if is_admin else "👤 User"
    await message.answer(
        f"👋 Welcome to *Advanced Media Streaming Bot*\n"
        f"Role: {role}\n\n"
        f"Use /help to see all available commands.",
        parse_mode="Markdown",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="Markdown")


# ─── RTMP Configuration ───────────────────────────────────────────────────────

@router.message(Command("set_rtmp"))
async def cmd_set_rtmp(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/set_rtmp rtmp_url stream_key`", parse_mode="Markdown")
        return
    parts = command.args.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Provide both RTMP URL and stream key.")
        return
    rtmp_url, stream_key = parts[0], parts[1]
    await _db.save_rtmp(message.from_user.id, rtmp_url, stream_key)
    await message.answer(
        f"✅ RTMP configured!\n`{rtmp_url}` / `{mask_key(stream_key)}`",
        parse_mode="Markdown",
    )


@router.message(Command("set_rtmp_key"))
async def cmd_set_rtmp_key(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/set_rtmp_key your_stream_key`", parse_mode="Markdown")
        return
    existing = await _db.get_rtmp(message.from_user.id)
    rtmp_url = existing["rtmp_url"] if existing else "rtmp://a.rtmp.youtube.com/live2"
    await _db.save_rtmp(message.from_user.id, rtmp_url, command.args.strip())
    await message.answer("✅ Stream key updated.", parse_mode="Markdown")


@router.message(Command("show_rtmp"))
async def cmd_show_rtmp(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    cfg = await _db.get_rtmp(message.from_user.id)
    if not cfg:
        await message.answer("⚠️ No RTMP config saved. Use /set\\_rtmp.", parse_mode="Markdown")
        return
    await message.answer(
        f"📡 *RTMP Config*\n"
        f"URL: `{cfg['rtmp_url']}`\n"
        f"Key: `{mask_key(cfg['stream_key'])}`",
        parse_mode="Markdown",
    )


# ─── Quality / Bitrate ────────────────────────────────────────────────────────

@router.message(Command("quality"))
async def cmd_quality(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args or command.args.strip() not in ("480", "720", "1080"):
        await message.answer("Usage: `/quality 480|720|1080`", parse_mode="Markdown")
        return
    q = int(command.args.strip())
    await _db.set_setting(f"quality_{message.from_user.id}", str(q))
    await message.answer(f"✅ Default quality set to *{q}p*.", parse_mode="Markdown")


@router.message(Command("bitrate"))
async def cmd_bitrate(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/bitrate 2500k`", parse_mode="Markdown")
        return
    vb = command.args.strip()
    await _db.set_setting(f"vbitrate_{message.from_user.id}", vb)
    await message.answer(f"✅ Default video bitrate set to `{vb}`.", parse_mode="Markdown")


# ─── User management ──────────────────────────────────────────────────────────

@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/ban user_id`", parse_mode="Markdown")
        return
    try:
        uid = int(command.args.strip())
        await _db.set_user_role(uid, "banned")
        await message.answer(f"🚫 User `{uid}` banned.", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Invalid user ID.")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/unban user_id`", parse_mode="Markdown")
        return
    try:
        uid = int(command.args.strip())
        await _db.set_user_role(uid, "user")
        await message.answer(f"✅ User `{uid}` unbanned.", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Invalid user ID.")


@router.message(Command("promote"))
async def cmd_promote(message: Message, command: CommandObject, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/promote user_id`", parse_mode="Markdown")
        return
    try:
        uid = int(command.args.strip())
        await _db.set_user_role(uid, "admin")
        await message.answer(f"👑 User `{uid}` promoted to admin.", parse_mode="Markdown")
    except ValueError:
        await message.answer("⚠️ Invalid user ID.")


# ─── Broadcast ────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(
    message: Message, command: CommandObject, is_admin: bool = False
) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    if not command.args:
        await message.answer("Usage: `/broadcast your message`", parse_mode="Markdown")
        return
    db = _db.get_db()
    async with db.execute("SELECT id FROM users WHERE role != 'banned'") as cur:
        rows = await cur.fetchall()
    text    = command.args.strip()
    success = 0
    failed  = 0
    bot     = message.bot
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    for row in rows:
        uid = row["id"]
        try:
            await bot.send_message(uid, f"📢 *Broadcast:*\n{text}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05) # 20 msg/sec limit
        except Exception as e:
            logger.error("Failed to send broadcast to %s: %s", uid, e)
            failed += 1
    await message.answer(f"✅ Broadcast finished.\nSent: {success}\nFailed: {failed}")


# ─── Stats & Logs ─────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    db = _db.get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        total_users = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM stream_sessions") as cur:
        total_sessions = (await cur.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM stream_sessions WHERE status='running'") as cur:
        running_sessions = (await cur.fetchone())[0]
    await message.answer(
        f"📊 *Bot Statistics*\n"
        f"👤 Total users   : {total_users}\n"
        f"📺 Total sessions : {total_sessions}\n"
        f"🟢 Active streams : {running_sessions}",
        parse_mode="Markdown",
    )


@router.message(Command("logs"))
async def cmd_logs(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        await message.answer("⛔ Admin only.")
        return
    db = _db.get_db()
    async with db.execute(
        "SELECT level, message, created_at FROM logs ORDER BY id DESC LIMIT 20"
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        await message.answer("📭 No logs yet.")
        return
    lines = [f"`[{r['level']}]` {r['message']} _({r['created_at']})_" for r in rows]
    await message.answer("\n".join(lines), parse_mode="Markdown")
