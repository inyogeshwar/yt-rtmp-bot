# YT RTMP Telegram Bot

Stream video/audio to YouTube Live directly from Telegram.

## Features

- Upload video from Telegram
- Upload audio from Telegram
- YouTube link support
- 24/7 loop
- Simple commands

## Install

apt update
apt install ffmpeg python3-pip -y

pip install -r requirements.txt

export BOT_TOKEN=YOUR_TOKEN
python app.py

## Commands

/start
/setkey STREAM_KEY
/upload (send file)
/source URL
/startlive
/stop
/status
