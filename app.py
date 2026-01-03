# ==================================================
# KATABUMP FREE RTMP BOT – FINAL v2 (4-DAY SAFE)
# Auto Start • Auto Restore • Auto Restart • GitHub
# ==================================================

import os, json, signal, asyncio, subprocess, time, logging
from pathlib import Path

import psutil, gdown
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- BASIC CONFIG ----------------
BOT_TOKEN = "8278727216:AAGhf2yRZrNx3DVPS5rfmKRmPqNJqwwm9C8"
ADMIN_ID = 7176592290
PORT = 8080

QUALITY = {
    "scale": "640:360",   # FREE SAFE
    "fps": "20",
    "vb": "550k",
    "ab": "64k",
}

BASE = Path(".")
STORE = BASE / "storage"
STORE.mkdir(exist_ok=True)

ACTIVE = {}
logging.basicConfig(level=logging.INFO)

# ---------------- HELPERS ----------------
def is_admin(update: Update):
    return update.effective_user and update.effective_user.id == ADMIN_ID

def cdir(cid: int):
    p = STORE / str(cid)
    p.mkdir(exist_ok=True)
    return p

def cfgp(cid: int):
    return cdir(cid) / "cfg.json"

def load_cfg(cid: int):
    return json.loads(cfgp(cid).read_text()) if cfgp(cid).exists() else {}

def save_cfg(cid: int, d: dict):
    cfgp(cid).write_text(json.dumps(d))

def cleanup(cid: int):
    """Auto disk cleanup (logs)"""
    d = cdir(cid)
    for f in d.glob("*.log"):
        if f.stat().st_size > 5 * 1024 * 1024:
            f.unlink(missing_ok=True)

# ---------------- BASIC COMMANDS ----------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Katabump RTMP Bot v2\n"
        "/panel\n/help\n/status\n/stats"
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 HELP (Short)\n\n"
        "/setkey KEY\n"
        "/setbackup GDRIVE\n"
        "/autostart\n"
        "/start\n"
        "/stop\n"
        "/panel\n\n"
        "Notes:\n"
        "• Free plan: 360p\n"
        "• Single live only\n"
        "• Renew every 4 days"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ACTIVE:
        cpu = psutil.cpu_percent()
        await update.message.reply_text(
            f"✅ LIVE\nCPU {cpu}%\nQuality 360p"
        )
    else:
        await update.message.reply_text("💤 Offline")

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().used // (1024 * 1024)
    await update.message.reply_text(f"CPU {cpu}%\nRAM {ram} MB")

# ---------------- ADMIN PANEL ----------------
async def panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    kb = [
        [
            InlineKeyboardButton("▶", callback_data="go"),
            InlineKeyboardButton("■", callback_data="stop"),
        ],
        [InlineKeyboardButton("📊", callback_data="stats")],
    ]
    await update.message.reply_text(
        "🎛 Admin Panel",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def panel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    fake = Update(
        update.update_id,
        message=q.message,
        effective_user=q.from_user,
        effective_chat=q.message.chat,
    )

    if q.data == "go":
        await start_stream(fake, None)
    elif q.data == "stop":
        await stop_stream(fake, None)
    elif q.data == "stats":
        await stats(fake, None)

# ---------------- SETUP COMMANDS ----------------
async def setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not ctx.args:
        return
    cid = update.effective_chat.id
    cfg = load_cfg(cid)
    cfg["key"] = ctx.args[0]
    save_cfg(cid, cfg)
    await update.message.reply_text("✅ KEY OK")

async def setbackup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not ctx.args:
        return
    cid = update.effective_chat.id
    cfg = load_cfg(cid)
    cfg["gdrive"] = ctx.args[0]
    save_cfg(cid, cfg)
    await update.message.reply_text("✅ BACKUP OK")

async def autostart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    cid = update.effective_chat.id
    cfg = load_cfg(cid)
    cfg["auto"] = time.time()
    cfg["renew_time"] = time.time()
    save_cfg(cid, cfg)
    await update.message.reply_text("✅ AUTO ON")

# ---------------- STREAM CORE ----------------
async def watch_stream(cid: int, update: Update):
    """Auto-restart on drop (with limit)"""
    while True:
        await asyncio.sleep(10)
        p = ACTIVE.get(cid)
        if not p:
            return
        if p.poll() is not None:
            ACTIVE.pop(cid, None)
            cfg = load_cfg(cid)
            cfg["restarts"] = cfg.get("restarts", 0) + 1
            save_cfg(cid, cfg)

            if cfg["restarts"] > 5:
                await update.message.reply_text("❌ Too many restarts, stopped")
                return

            await update.message.reply_text("⚠️ Dropped → Restarting")
            await start_stream(update, None)
            return

async def restore_video(cid: int):
    """Auto restore video from Google Drive"""
    cfg = load_cfg(cid)
    if "gdrive" not in cfg:
        return

    v = cdir(cid) / "video.mp4"
    if v.exists() and v.stat().st_size > 5_000_000:
        return

    if v.exists():
        v.unlink(missing_ok=True)

    await asyncio.to_thread(
        gdown.download,
        cfg["gdrive"],
        str(v),
        quiet=False,
        fuzzy=True,
    )

async def start_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    cid = update.effective_chat.id
    if ACTIVE:
        return

    cfg = load_cfg(cid)
    if "key" not in cfg:
        return await update.message.reply_text("❌ NO KEY")

    await restore_video(cid)

    v = cdir(cid) / "video.mp4"
    if not v.exists():
        return await update.message.reply_text("❌ NO VIDEO")

    cleanup(cid)

    rtmp = f"rtmp://a.rtmp.youtube.com/live2/{cfg['key']}"
    logf = open(cdir(cid) / "ffmpeg.log", "w")

    cmd = [
        "ffmpeg",
        "-re",
        "-stream_loop", "-1",
        "-r", QUALITY["fps"],
        "-i", str(v),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-threads", "1",
        "-vf", f"scale={QUALITY['scale']}",
        "-b:v", QUALITY["vb"],
        "-maxrate", QUALITY["vb"],
        "-bufsize", "1100k",
        "-g", "40",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", QUALITY["ab"],
        "-ar", "44100",
        "-f", "flv",
        rtmp,
    ]

    p = subprocess.Popen(
        cmd,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    ACTIVE[cid] = p
    asyncio.create_task(watch_stream(cid, update))
    await update.message.reply_text("🚀 LIVE")

async def stop_stream(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    cid = update.effective_chat.id
    p = ACTIVE.get(cid)
    if p:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        ACTIVE.clear()
        await update.message.reply_text("⏹ STOPPED")

# ---------------- RENEW REMINDER ----------------
async def renew_reminder(app):
    while True:
        await asyncio.sleep(3600)  # hourly
        now = time.time()
        for d in STORE.iterdir():
            if not d.is_dir():
                continue
            cid = int(d.name)
            cfg = load_cfg(cid)
            rt = cfg.get("renew_time")
            if not rt or cfg.get("reminded"):
                continue
            if now - rt > 259200:  # 3 days
                cfg["reminded"] = True
                save_cfg(cid, cfg)
                await app.bot.send_message(
                    ADMIN_ID,
                    "⚠️ Katabump Free server expires soon.\nRenew before 4 days!",
                )

# ---------------- KEEP ALIVE + AUTO BOOT ----------------
async def post_init(app):
    webapp = web.Application()
    webapp.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(webapp)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    asyncio.create_task(renew_reminder(app))

    await asyncio.sleep(5)
    for d in STORE.iterdir():
        if d.is_dir():
            cid = int(d.name)
            cfg = load_cfg(cid)
            if cfg.get("auto") and cfg.get("key"):
                class Dummy:
                    effective_chat = type("c", (), {"id": cid})
                    effective_user = type("u", (), {"id": ADMIN_ID})
                    message = None
                await start_stream(Dummy(), None)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("panel", panel))
    app.add_handler(CallbackQueryHandler(panel_cb))

    app.add_handler(CommandHandler("setkey", setkey))
    app.add_handler(CommandHandler("setbackup", setbackup))
    app.add_handler(CommandHandler("autostart", autostart))
    app.add_handler(CommandHandler("start", start_stream))
    app.add_handler(CommandHandler("stop", stop_stream))

    app.run_polling()

if __name__ == "__main__":
    main()
