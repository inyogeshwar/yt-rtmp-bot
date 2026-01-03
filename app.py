# ===============================
# TELEGRAM RTMP STREAM BOT
# Free Plan • Stable • Auto CPU • 4-Day Alert
# ===============================

import os, signal, asyncio, subprocess, json, html, logging, time
from pathlib import Path
from collections import deque

from aiohttp import web
import gdown, psutil

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# -------------------------------
# BASIC CONFIG
# -------------------------------
BOT_TOKEN = "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE"
PORT = 8080
CPU_LIMIT = 22  # safe for Katabump Free

BASE = Path(".")
STORAGE = BASE / "storage"
STORAGE.mkdir(exist_ok=True)

VIDEO_EXT = {".mp4", ".mkv", ".mov"}
AUDIO_EXT = {".mp3", ".aac", ".wav", ".m4a"}
MAX_SIZE = 200 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("RTMP")

ACTIVE = {}    # chat_id -> ffmpeg process
QUALITY = {}   # chat_id -> LOW / MED

# -------------------------------
# HELPERS
# -------------------------------
def cdir(cid):
    p = STORAGE / str(cid)
    p.mkdir(exist_ok=True)
    return p

def cfg_path(cid):
    return cdir(cid) / "config.json"

def load_cfg(cid):
    return json.loads(cfg_path(cid).read_text()) if cfg_path(cid).exists() else {}

def save_cfg(cid, d):
    cfg_path(cid).write_text(json.dumps(d))

# -------------------------------
# COMMANDS
# -------------------------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎥 RTMP Live Bot\n\n"
        "/set_stream <YT_KEY>\n"
        "/set_backup <GDRIVE_LINK>\n"
        "/start_stream\n"
        "/stop_stream\n"
        "/status\n"
        "/help"
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 COMMANDS\n\n"
        "/set_stream  → YouTube key\n"
        "/set_backup  → Google Drive video\n"
        "/start_stream → Start live\n"
        "/stop_stream  → Stop live\n"
        "/status       → CPU / Quality\n"
    )

async def set_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_stream YT_KEY")

    cfg = load_cfg(update.effective_chat.id)
    cfg["key"] = ctx.args[0]

    # 4-day timer start
    cfg["renew_time"] = time.time()
    cfg["alert_sent"] = False

    save_cfg(update.effective_chat.id, cfg)
    await update.message.reply_text("✅ Stream key saved\n⏰ 4-day timer started")

async def set_backup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await update.message.reply_text("Usage: /set_backup GDRIVE_LINK")

    cfg = load_cfg(update.effective_chat.id)
    cfg["backup"] = ctx.args[0]
    save_cfg(update.effective_chat.id, cfg)

    await update.message.reply_text("✅ Google Drive backup saved")

# -------------------------------
# FILE UPLOAD
# -------------------------------
async def upload_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    m = update.message
    f = m.video or m.audio or m.document
    if not f or f.file_size > MAX_SIZE:
        return

    ext = Path(f.file_name or "").suffix.lower()
    if ext in VIDEO_EXT:
        out = cdir(m.chat.id) / "video.mp4"
    elif ext in AUDIO_EXT:
        out = cdir(m.chat.id) / "audio.mp3"
    else:
        return

    tf = await f.get_file()
    await tf.download_to_drive(out)
    await m.reply_text("✅ File saved")

# -------------------------------
# GOOGLE DRIVE RESTORE
# -------------------------------
async def restore_video(cid):
    cfg = load_cfg(cid)
    link = cfg.get("backup")
    if not link:
        return

    v = cdir(cid) / "video.mp4"
    if v.exists() and v.stat().st_size > 5_000_000:
        return

    if v.exists():
        v.unlink()

    await asyncio.to_thread(
        gdown.download,
        link,
        str(v),
        quiet=False,
        fuzzy=True
    )

# -------------------------------
# FFMPEG PROFILES
# -------------------------------
def ffmpeg_cmd(v, rtmp, level):
    if level == "LOW":  # 240p SAFE
        return [
            "ffmpeg","-re","-stream_loop","-1","-i",str(v),
            "-c:v","libx264","-preset","ultrafast","-threads","1",
            "-vf","scale=426:240","-r","15",
            "-b:v","350k","-maxrate","350k","-bufsize","700k",
            "-c:a","aac","-b:a","48k","-ar","22050",
            "-f","flv",rtmp
        ]
    else:               # 360p LIMIT
        return [
            "ffmpeg","-re","-stream_loop","-1","-i",str(v),
            "-c:v","libx264","-preset","ultrafast","-threads","1",
            "-vf","scale=640:360","-r","20",
            "-b:v","600k","-maxrate","600k","-bufsize","1200k",
            "-c:a","aac","-b:a","64k","-ar","32000",
            "-f","flv",rtmp
        ]

# -------------------------------
# STREAM CONTROL
# -------------------------------
async def start_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    if cid in ACTIVE and ACTIVE[cid].poll() is None:
        return await update.message.reply_text("⚠️ Already live")

    cfg = load_cfg(cid)
    if "key" not in cfg:
        return await update.message.reply_text("❌ Set stream key first")

    await restore_video(cid)
    v = cdir(cid) / "video.mp4"
    if not v.exists():
        return await update.message.reply_text("❌ video.mp4 missing")

    rtmp = f"rtmp://a.rtmp.youtube.com/live2/{cfg['key']}"

    QUALITY[cid] = "LOW"
    p = subprocess.Popen(
        ffmpeg_cmd(v, rtmp, "LOW"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    ACTIVE[cid] = p

    asyncio.create_task(auto_quality(cid, v, rtmp))
    await update.message.reply_text("🚀 Live started (Auto Quality)")

async def auto_quality(cid, v, rtmp):
    while cid in ACTIVE and ACTIVE[cid].poll() is None:
        await asyncio.sleep(10)
        cpu = psutil.cpu_percent()
        target = "LOW" if cpu > CPU_LIMIT else "MED"

        if QUALITY.get(cid) != target:
            try:
                os.killpg(os.getpgid(ACTIVE[cid].pid), signal.SIGTERM)
            except:
                pass

            p = subprocess.Popen(
                ffmpeg_cmd(v, rtmp, target),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            ACTIVE[cid] = p
            QUALITY[cid] = target

async def stop_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    p = ACTIVE.get(cid)
    if not p:
        return await update.message.reply_text("⚠️ Not running")

    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except:
        pass

    ACTIVE.pop(cid, None)
    await update.message.reply_text("⏹ Stopped")

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    cpu = psutil.cpu_percent()
    q = QUALITY.get(cid, "-")
    live = cid in ACTIVE and ACTIVE[cid].poll() is None
    await update.message.reply_text(
        f"{'LIVE' if live else 'OFF'}\nCPU: {cpu}%\nQuality: {q}"
    )

# -------------------------------
# 4-DAY RENEW ALERT
# -------------------------------
async def renew_alert_task(app):
    while True:
        await asyncio.sleep(3600)
        now = time.time()

        for d in STORAGE.iterdir():
            if not d.is_dir():
                continue

            cid = int(d.name)
            cfg = load_cfg(cid)

            rt = cfg.get("renew_time")
            if not rt or cfg.get("alert_sent"):
                continue

            if now - rt >= 259200:  # 3 days
                try:
                    await app.bot.send_message(
                        chat_id=cid,
                        text=(
                            "⚠️ RENEW ALERT\n\n"
                            "Server 4 din me delete hoga.\n"
                            "👉 Abhi naya server bana lo."
                        )
                    )
                except:
                    pass

                cfg["alert_sent"] = True
                save_cfg(cid, cfg)

# -------------------------------
# WEB KEEP ALIVE
# -------------------------------
async def start_web(app):
    w = web.Application()
    w.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(w)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

async def post_init(app):
    await start_web(app)
    asyncio.create_task(renew_alert_task(app))

# -------------------------------
# MAIN
# -------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("set_stream", set_stream))
    app.add_handler(CommandHandler("set_backup", set_backup))
    app.add_handler(CommandHandler("start_stream", start_stream))
    app.add_handler(CommandHandler("stop_stream", stop_stream))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.ALL, upload_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
