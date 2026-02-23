# ===============================
# TELEGRAM IMAGE → YOUTUBE LIVE BOT
# Image + MP3 (Drive/Telegram)
# Katabump Free • Low CPU • Stable
# ===============================

import os
import signal
import subprocess
import json
import asyncio
from pathlib import Path

import gdown
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------------------
# CONFIG
# -------------------------------
BOT_TOKEN = "your-token"
PORT = 8080

BASE = Path(".")
STORAGE = BASE / "storage"
STORAGE.mkdir(exist_ok=True)

ACTIVE = {}  # chat_id -> ffmpeg process

# -------------------------------
# HELPERS
# -------------------------------
def chat_dir(cid: int) -> Path:
    d = STORAGE / str(cid)
    d.mkdir(exist_ok=True)
    return d

def cfg_path(cid: int) -> Path:
    return chat_dir(cid) / "config.json"

def load_cfg(cid: int) -> dict:
    if cfg_path(cid).exists():
        return json.loads(cfg_path(cid).read_text())
    return {}

def save_cfg(cid: int, data: dict):
    cfg_path(cid).write_text(json.dumps(data))

# -------------------------------
# COMMANDS
# -------------------------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎥 Image → YouTube Live Bot\n\n"
        "/set_stream <YT_KEY>\n"
        "/set_audio <GDRIVE_MP3_LINK>\n"
        "/start_stream\n"
        "/stop_stream\n"
        "/status\n\n"
        "📌 Send IMAGE + MP3 first"
    )

async def set_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_stream <YT_KEY>")

    cfg = load_cfg(update.effective_chat.id)
    cfg["key"] = ctx.args[0]
    save_cfg(update.effective_chat.id, cfg)

    await update.message.reply_text("✅ Stream key saved")

async def set_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_audio <gdrive_mp3_link>")

    cid = update.effective_chat.id
    d = chat_dir(cid)
    out = d / "audio.mp3"

    await update.message.reply_text("⬇️ Downloading MP3 from Google Drive...")

    try:
        if out.exists():
            out.unlink()

        await asyncio.to_thread(
            gdown.download,
            ctx.args[0],
            str(out),
            quiet=False,
            fuzzy=True
        )

        if out.exists() and out.stat().st_size > 1_000_000:
            await update.message.reply_text("✅ MP3 saved from Google Drive")
        else:
            await update.message.reply_text("❌ Download failed (check link)")
    except Exception as e:
        await update.message.reply_text("❌ Failed to download MP3")

# -------------------------------
# FILE UPLOAD (IMAGE / SMALL MP3)
# -------------------------------
async def upload_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    cid = msg.chat.id
    d = chat_dir(cid)

    # IMAGE
    if msg.photo:
        photo = msg.photo[-1]
        f = await photo.get_file()
        await f.download_to_drive(d / "image.jpg")
        return await msg.reply_text("🖼️ Image saved")

    # MP3 (Telegram limit safe)
    f = msg.audio or msg.document
    if not f:
        return

    if f.file_size and f.file_size > 20 * 1024 * 1024:
        return await msg.reply_text(
            "❌ MP3 too large for Telegram.\n"
            "👉 Use Google Drive:\n"
            "/set_audio <drive_link>"
        )

    name = (f.file_name or "").lower()
    if not name.endswith(".mp3"):
        return await msg.reply_text("❌ Only MP3 allowed")

    try:
        file = await f.get_file()
        await file.download_to_drive(d / "audio.mp3")
        await msg.reply_text("🎵 MP3 saved")
    except:
        await msg.reply_text("❌ Failed to save MP3")

# -------------------------------
# START STREAM (IMAGE + MP3)
# -------------------------------
async def start_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id

    if cid in ACTIVE and ACTIVE[cid].poll() is None:
        return await update.message.reply_text("⚠️ Stream already running")

    cfg = load_cfg(cid)
    if "key" not in cfg:
        return await update.message.reply_text("❌ Set stream key first")

    d = chat_dir(cid)
    image = d / "image.jpg"
    audio = d / "audio.mp3"

    if not image.exists() or not audio.exists():
        return await update.message.reply_text("❌ Send IMAGE + MP3 first")

    rtmp = f"rtmp://a.rtmp.youtube.com/live2/{cfg['key']}"

    cmd = [
        "ffmpeg",
        "-re",
        "-loop", "1",
        "-i", str(image),
        "-stream_loop", "-1",
        "-i", str(audio),

        # ---- IMAGE → ANIMATED VIDEO ----
        "-vf", "zoompan=z='min(zoom+0.0005,1.05)':d=125",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "stillimage",
        "-profile:v", "baseline",
        "-level", "3.0",
        "-pix_fmt", "yuv420p",
        "-r", "15",
        "-g", "30",
        "-s", "426x240",
        "-b:v", "300k",
        "-maxrate", "300k",
        "-bufsize", "600k",

        # ---- AUDIO (FIXED 128 KBPS) ----
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "44100",

        "-f", "flv",
        rtmp
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    ACTIVE[cid] = proc
    await update.message.reply_text("🚀 Live started (Image + MP3)")

# -------------------------------
# STOP / STATUS
# -------------------------------
async def stop_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    proc = ACTIVE.get(cid)

    if not proc:
        return await update.message.reply_text("⚠️ Not running")

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except:
        pass

    ACTIVE.pop(cid, None)
    await update.message.reply_text("⏹ Stream stopped")

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    live = cid in ACTIVE and ACTIVE[cid].poll() is None
    await update.message.reply_text("✅ LIVE" if live else "💤 Offline")

# -------------------------------
# MAIN
# -------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_stream", set_stream))
    app.add_handler(CommandHandler("set_audio", set_audio))
    app.add_handler(CommandHandler("start_stream", start_stream))
    app.add_handler(CommandHandler("stop_stream", stop_stream))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.ALL, upload_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
