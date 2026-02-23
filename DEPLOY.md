# Platform Deployment Guide

## Required Environment Variables (set on every platform)

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your Telegram bot token |
| `ADMIN_IDS` | Comma-separated Telegram user IDs |

All other variables are optional (defaults apply).

---

## Render

1. Push this repo to GitHub / GitLab.
2. Go to **render.com → New → Blueprint** and connect the repo.
   - Render auto-reads `render.yaml` and creates a **Worker** service.
3. Set secrets in **Environment → Secret Files or Env Vars**:
   - `BOT_TOKEN`, `ADMIN_IDS`
4. Click **Deploy**.
5. Persistent disk (`/app/storage`, 10 GB) is declared in `render.yaml` — SQLite + downloads survive restarts.

> Build method: **Docker** (`Dockerfile` → linux/amd64 with ffmpeg pre-installed)

---

## Railway

1. Push repo to GitHub.
2. Go to **railway.app → New Project → Deploy from GitHub Repo**.
3. Railway auto-detects `nixpacks.toml` (installs Python 3.11 + ffmpeg via Nix).
4. Open **Variables** tab, add:
   - `BOT_TOKEN`, `ADMIN_IDS`
5. Click **Deploy**.

> **Storage note:** Railway volumes are available on paid plans. On the free tier the filesystem is ephemeral — DB resets on restart. Upgrade and mount a volume at `/app/storage` to persist data.

> Build method: **Nixpacks** (reads `nixpacks.toml`)

---

## Koyeb

1. Push repo to GitHub.
2. Go to **koyeb.com → Create Service → GitHub**.
3. Select repository, branch `main`.
4. Set builder to **Dockerfile**.
5. Set **Service type → Worker**.
6. Under **Environment variables**, add:
   - `BOT_TOKEN` (mark secret), `ADMIN_IDS` (mark secret)
7. Click **Deploy**.

> Build method: **Docker** (`Dockerfile` → linux/amd64)
> Storage is ephemeral on Koyeb. Use an external DB (e.g. Turso / PlanetScale) for production persistence.

---

## Heroku

### One-time setup

```bash
# Install Heroku CLI, then:
heroku login
heroku create your-bot-name

# Add buildpacks (apt first for ffmpeg, then Python)
heroku buildpacks:add --index 1 heroku-community/apt
heroku buildpacks:add --index 2 heroku/python

# Set environment variables
heroku config:set BOT_TOKEN=your_token_here
heroku config:set ADMIN_IDS=123456789,987654321

# Deploy
git push heroku main

# Scale worker dyno (Procfile defines `worker`)
heroku ps:scale worker=1
```

### Files used

| File | Purpose |
|---|---|
| `Procfile` | `worker: python app.py` — tells Heroku process type |
| `runtime.txt` | `python-3.11.9` — pins Python version |
| `Aptfile` | `ffmpeg` — installed by `heroku-community/apt` buildpack |

> **Storage note:** Heroku ephemeral filesystem — all files lost on dyno restart. For persistent storage attach a Heroku Postgres addon and switch `DATABASE_URL` to a PostgreSQL connection string (requires code change to use `asyncpg` instead of `aiosqlite`).

---

## Persistent Storage Summary

| Platform | Persistence | Notes |
|---|---|---|
| **Render** | ✅ Persistent Disk | Declared in `render.yaml` (10 GB, `/app/storage`) |
| **Railway** | ⚠️ Paid plan only | Add volume at `/app/storage` in Railway dashboard |
| **Koyeb** | ❌ Ephemeral | Use external DB / object storage for production |
| **Heroku** | ❌ Ephemeral | Attach Heroku Postgres or Cloudcube S3 |
| **Docker / VPS** | ✅ Named volume | `bot_storage` in `docker-compose.yml` |

---

## Environment Variables Quick Reference

```env
BOT_TOKEN=           # required
ADMIN_IDS=           # required – comma-separated IDs
DEFAULT_RTMP_URL=rtmp://a.rtmp.youtube.com/live2
DEFAULT_STREAM_KEY=
DEFAULT_QUALITY=720
DEFAULT_VIDEO_BITRATE=2500k
DEFAULT_AUDIO_BITRATE=128k
RATE_LIMIT_CALLS=5
RATE_LIMIT_PERIOD=60
LOG_LEVEL=INFO
STORAGE_PATH=./storage
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
```
