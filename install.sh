#!/bin/bash
set -e

echo "🚀 Installing YT RTMP BOT"

apt update
apt install -y python3 python3-pip ffmpeg git

mkdir -p /opt/ytbot
cd /opt/ytbot

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "✅ Done!"
echo ""
echo "Run:"
echo "export BOT_TOKEN=YOUR_TOKEN"
echo "python app.py"
