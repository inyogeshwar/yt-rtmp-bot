# Katabump Free YouTube Live Bot

Telegram-controlled YouTube RTMP bot optimized for **Katabump Free (25% CPU)**.

## Features
- Auto YouTube Live
- Auto CPU-based quality (240p ↔ 360p)
- Google Drive video backup
- Auto restore after server delete
- 4-day renew alert (Day-3 warning)
- Low RAM / Low CPU

## Requirements
- Python 3.11
- ffmpeg installed
- Telegram Bot Token
- YouTube Stream Key
- Google Drive video link

## Setup (2 Minutes)
```bash
git clone https://github.com/inyogeshwar/katabump-free-rtmp-bot
cd katabump-rtmp-bot
pip install -r requirements.txt
python app.py
````

## Telegram Commands

```
/set_stream YT_KEY
/set_backup GDRIVE_LINK
/start_stream
/stop_stream
/status
/help
```

## YouTube Setup

* YouTube Studio → Create Live
* Copy Stream Key
* Paste using /set_stream

## Free Plan Flow (Every 4 Days)

1. Bot sends alert on Day-3
2. Create new Katabump server
3. Clone repo
4. Start bot
5. Live auto restored

## Useful Links

* Dashboard: [https://dashboard.katabump.com/](https://dashboard.katabump.com/)
* Status: [https://status.katabump.com/](https://status.katabump.com/)
* Control: [https://control.katabump.com/](https://control.katabump.com/)

## Notes

* 480p not supported on free plan
* 24/7 requires paid plan

```
