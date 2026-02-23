import os
import subprocess
import asyncio
import signal
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN") or "PASTE_TOKEN"

BASE = Path.cwd()
STORAGE = BASE / "storage"
STORAGE.mkdir(exist_ok=True)

STREAM_KEY = None
SOURCE_FILE = None
PROCESS = None


def get_stream_url(url):
    if url.startswith("http"):
        try:
            cmd = ["yt-dlp", "-f", "best", "-g", url]
            return subprocess.check_output(cmd).decode().strip()
        except:
            return url
    return url


def start_stream():
    global PROCESS

    if not STREAM_KEY or not SOURCE_FILE:
        return False, "Set key and source first"

    rtmp = f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
    media = get_stream_url(str(SOURCE_FILE))

    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-i", media,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-f", "flv",
        rtmp
    ]

    PROCESS = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True, "🚀 Live Started"


def stop_stream():
    global PROCESS
    if PROCESS:
        try:
            os.killpg(os.getpgid(PROCESS.pid), signal.SIGTERM)
        except:
            pass
        PROCESS = None


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = """
🎥 YT RTMP BOT

Commands:
/setkey STREAM_KEY
/upload (send video/audio)
/source URL
/startlive
/stop
/status
"""
    await update.message.reply_text(text)


async def setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global STREAM_KEY
    if not ctx.args:
        return await update.message.reply_text("Send /setkey KEY")
    STREAM_KEY = ctx.args[0]
    await update.message.reply_text("✅ Stream key saved")


async def source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global SOURCE_FILE
    if not ctx.args:
        return await update.message.reply_text("Send URL")
    SOURCE_FILE = ctx.args[0]
    await update.message.reply_text("✅ Source URL saved")


async def handle_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global SOURCE_FILE

    file = update.message.video or update.message.audio or update.message.document
    if not file:
        return

    tg_file = await file.get_file()
    path = STORAGE / f"{file.file_id}.dat"

    await tg_file.download_to_drive(path)
    SOURCE_FILE = path

    await update.message.reply_text("✅ File uploaded & selected")


async def startlive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ok, msg = start_stream()
    await update.message.reply_text(msg)


async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stop_stream()
    await update.message.reply_text("🛑 Stopped")


async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if PROCESS:
        await update.message.reply_text("🟢 LIVE RUNNING")
    else:
        await update.message.reply_text("🔴 STOPPED")


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setkey", setkey))
    app.add_handler(CommandHandler("source", source))
    app.add_handler(CommandHandler("startlive", startlive))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.Document.ALL, handle_upload))

    print("Bot running...")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
