# Advanced Telegram Media Streaming & Processing Bot

A production-ready Telegram bot for media downloading, FFmpeg processing, and YouTube Live (RTMP) streaming — controlled entirely from Telegram chat.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/inyogeshwar/yt-rtmp-bot)
[![Deploy to Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/inyogeshwar/yt-rtmp-bot)
[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&repository=github.com/inyogeshwar/yt-rtmp-bot&branch=main&name=yt-rtmp-bot)
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://www.heroku.com/deploy/?template=https://github.com/inyogeshwar/yt-rtmp-bot)

---

## Features

| Category | Details |
|---|---|
| **Media Input** | Telegram files, YouTube links, Google Drive links, direct URLs |
| **Auto Detection** | FFprobe-based codec / stream / audio-presence detection |
| **RTMP Streaming** | FFmpeg push to YouTube Live (or any RTMP endpoint) |
| **Multiple Streams** | Concurrent sessions, each with a unique ID |
| **Quality Control** | 480p / 720p / 1080p + custom bitrate |
| **yt-dlp** | YouTube / playlist download, MP3 extraction, format selection |
| **Playlist** | Queue system, auto-advance, loop mode |
| **Processing** | Convert, extract audio, thumbnail, watermark, speed change |
| **Auto Restart** | Crash detection + configurable auto-restart per session |
| **Reply Keywords** | `live`, `mp3`, `720`, `info`, `thumbnail`, `stop`, `loop` |
| **Admin System** | Whitelist-based admin roles, ban/promote users, broadcast |
| **Rate Limiting** | Per-user token-bucket rate limiter |
| **Database** | Async SQLite (aiosqlite) for users, sessions, playlist, settings |
| **Logging** | File + Telegram notification on crash |
| **Deployment** | VPS, Docker, docker-compose |

---

## Folder Structure

```
yt-rtmp-bot/
├── app.py                    # Entry point
├── config.py                 # All settings (reads .env)
├── .env.example              # Environment variable template
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── bot/
│   ├── main.py               # Bot init, dispatcher, startup/shutdown
│   ├── handlers/
│   │   ├── admin.py          # /start /help /set_rtmp /quality /ban …
│   │   ├── media.py          # File uploads, URL input, /convert_mp4 …
│   │   ├── stream.py         # /start_stream /stop_stream /status …
│   │   ├── downloader.py     # /yt /ytmp3 /ytbest /ytinfo …
│   │   ├── playlist.py       # /add /remove /list /clear …
│   │   └── keywords.py       # Reply keyword parser
│   ├── services/
│   │   ├── file_detector.py  # FFprobe wrapper → MediaInfo
│   │   ├── ffmpeg_service.py # FFmpeg processing & RTMP streaming
│   │   ├── stream_manager.py # Session lifecycle + auto-restart
│   │   ├── ytdlp_service.py  # yt-dlp async helpers
│   │   └── gdrive_service.py # Google Drive download
│   ├── database/
│   │   ├── models.py         # SQL schema
│   │   └── db.py             # Async CRUD operations
│   ├── middlewares/
│   │   ├── auth.py           # User upsert + role check
│   │   └── rate_limit.py     # Token-bucket rate limiter
│   └── utils/
│       ├── helpers.py        # URL detection, formatting
│       ├── progress.py       # Telegram progress bar
│       └── security.py       # Admin check, key masking, XOR encryption
└── storage/
    ├── downloads/            # All downloaded / converted files
    ├── thumbnails/           # Background images, extracted thumbnails
    └── logs/                 # bot.log
```

---

## Quick Start (VPS / Local)

### 1. Prerequisites

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg python3.11 python3-pip git

# Verify
ffmpeg -version
python3.11 --version
```

### 2. Clone & Configure

```bash
git clone https://github.com/youruser/yt-rtmp-bot.git
cd yt-rtmp-bot

cp .env.example .env
nano .env          # Fill in BOT_TOKEN and ADMIN_IDS
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python app.py
```

---

## Docker Deployment

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f bot

# Stop
docker compose down
```

---

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram Bot API token | **required** |
| `ADMIN_IDS` | Comma-separated admin user IDs | **required** |
| `DEFAULT_RTMP_URL` | RTMP server URL | `rtmp://a.rtmp.youtube.com/live2` |
| `DEFAULT_STREAM_KEY` | Stream key | — |
| `DEFAULT_QUALITY` | Stream quality (480/720/1080) | `720` |
| `DEFAULT_VIDEO_BITRATE` | Video bitrate | `2500k` |
| `DEFAULT_AUDIO_BITRATE` | Audio bitrate | `128k` |
| `RATE_LIMIT_CALLS` | Max requests per period | `5` |
| `RATE_LIMIT_PERIOD` | Period in seconds | `60` |
| `LOG_LEVEL` | Python log level | `INFO` |
| `STORAGE_PATH` | Base storage directory | `./storage` |

---

## Commands Reference

### Admin Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Full command list |
| `/set_rtmp <url> <key>` | Set RTMP URL and stream key |
| `/set_rtmp_key <key>` | Update stream key only |
| `/show_rtmp` | Display current RTMP config (key masked) |
| `/quality 480\|720\|1080` | Set default stream quality |
| `/bitrate 2500k` | Set default video bitrate |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/promote <user_id>` | Promote user to admin |
| `/broadcast <text>` | Send message to all users |
| `/stats` | Usage statistics |
| `/logs` | Recent bot logs |

### Stream Commands

| Command | Description |
|---|---|
| `/start_stream [path]` | Start streaming queued file |
| `/stop_stream [id]` | Stop stream (all or by session prefix) |
| `/pause_stream [id]` | Pause stream |
| `/resume_stream [id]` | Resume stream |
| `/status` | All active streams |
| `/sessions` | Your session history |
| `/loop` | Toggle loop mode |

### Download Commands

| Command | Description |
|---|---|
| `/yt <url>` | Download best quality video |
| `/ytmp3 <url>` | Download as MP3 |
| `/ytbest <url>` | Download best + show metadata |
| `/ytinfo <url>` | Show video info only |
| `/ytplaylist <url>` | Download full playlist |

### Processing Commands

| Command | Description |
|---|---|
| `/convert_mp4` | Re-encode last file to MP4 |
| `/extract_audio` | Extract audio from last file |
| `/thumbnail` | Extract thumbnail image |
| `/probe` | Show FFprobe info for last file |

### Playlist Commands

| Command | Description |
|---|---|
| `/add [path]` | Add file to playlist queue |
| `/remove <id>` | Remove item by ID |
| `/list` | Show current playlist |
| `/clear` | Clear playlist |
| `/playlist_stream` | Stream entire playlist |

### Reply Keywords

Reply to any media message with:

| Keyword | Action |
|---|---|
| `live` / `stream` | Start streaming the file |
| `mp3` / `audio` | Convert to MP3 |
| `720` / `480` / `1080` | Change quality setting |
| `info` / `probe` | Show FFprobe details |
| `thumbnail` / `thumb` | Extract and send thumbnail |
| `loop` | Toggle loop mode |
| `stop` | Stop all active streams |

---

## Example Usage

1. **Set up admin access** — Add your Telegram ID to `ADMIN_IDS` in `.env`
2. **Configure RTMP** — `/set_rtmp rtmp://a.rtmp.youtube.com/live2 your-stream-key`
3. **Send a video file** — Bot auto-detects codec, resolution, and audio presence
4. **Reply `live`** — Starts streaming immediately
5. **Download from YouTube** — `/yt https://youtube.com/watch?v=dQw4w9WgXcQ`
6. **Check status** — `/status`

### Audio-only stream

Send an MP3 → bot wraps it with a background image → stream starts as video+audio (required by YouTube Live).

### 24/7 Radio Mode

1. Download several MP3s via `/ytmp3`
2. `/add` each file to the playlist
3. `/loop` — enable loop mode
4. `/playlist_stream` — streams all files on repeat

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `BOT_TOKEN` missing | Create `.env` from `.env.example` and fill in the token |
| `ffmpeg: not found` | Install FFmpeg: `sudo apt install ffmpeg` |
| Stream crashes immediately | Check RTMP URL and stream key with /show_rtmp |
| YouTube 403 error | Ensure stream key is active in YouTube Studio |
| Large file not uploading | Telegram cap is 2 GB; use `/yt` to download instead |
| Google Drive download fails | File must be set to "Anyone with the link can view" |
| Rate limit errors | Admins are exempt; regular users get 5 cmd/60s |

---

## Security Notes

- Stream keys are stored in SQLite with XOR+base64 obfuscation; use a strong `BOT_TOKEN` environment.
- Only users in `ADMIN_IDS` can start/stop streams, set RTMP credentials, or broadcast.
- Banned users are silently ignored by the auth middleware.

---

## License

MIT
