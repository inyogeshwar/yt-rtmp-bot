#!/bin/bash
# Advanced Telegram Media Streaming Bot – Installer
# Usage: bash install.sh
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }

info "=== Advanced Telegram Media Streaming Bot – Installer ==="

# ── System dependencies ───────────────────────────────────────────────────────
info "Updating package list…"
apt-get update -qq

info "Installing system packages…"
apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip \
    ffmpeg \
    git curl wget ca-certificates rsync

ffmpeg -version | head -1 || error "FFmpeg installation failed"
ffprobe -version | head -1 || error "FFprobe not found"

# ── Python venv ───────────────────────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-/opt/yt-rtmp-bot}"
info "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

if [ ! -d "$INSTALL_DIR/venv" ]; then
    info "Creating Python virtual environment…"
    python3.11 -m venv "$INSTALL_DIR/venv"
fi

source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip -q

# Copy project files if running from the repo directory
if [ -f "requirements.txt" ]; then
    info "Copying project files to $INSTALL_DIR…"
    rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' . "$INSTALL_DIR/"
else
    warn "Run this script from the project root directory."
fi

info "Installing Python dependencies…"
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    pip install -r "$INSTALL_DIR/requirements.txt" -q
else
    error "requirements.txt not found in $INSTALL_DIR"
fi

# ── Environment file ──────────────────────────────────────────────────────────
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    warn ".env file created. Edit it now: nano $INSTALL_DIR/.env"
fi

# ── Default background image ──────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/storage/thumbnails"
python3 -c "
try:
    from PIL import Image
    img = Image.new('RGB', (1280, 720), color=(20, 20, 20))
    img.save('$INSTALL_DIR/storage/thumbnails/default_bg.jpg')
    print('Default background image created.')
except Exception as e:
    print(f'Skipping background image: {e}')
"

# ── Systemd service ───────────────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/yt-rtmp-bot.service"
info "Creating systemd service at $SERVICE_FILE…"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Advanced Telegram Media Streaming Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable yt-rtmp-bot

info "=== Installation complete! ==="
echo ""
echo "  1. Edit your config:   nano $INSTALL_DIR/.env"
echo "  2. Set BOT_TOKEN and ADMIN_IDS"
echo "  3. Start the bot:      systemctl start yt-rtmp-bot"
echo "  4. View logs:          journalctl -u yt-rtmp-bot -f"
echo ""
