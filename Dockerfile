# ─────────────────────────────────────────────────────────────────────────────
# Advanced Telegram Media Streaming Bot – Dockerfile
# Compatible with: Docker, Render, Railway, Koyeb, Heroku (container stack)
# ─────────────────────────────────────────────────────────────────────────────
# Force linux/amd64 so ffmpeg static binaries work on all cloud platforms
FROM --platform=linux/amd64 python:3.11-slim

# ─── System dependencies ─────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        wget \
        curl \
        git \
        ca-certificates \
    && ffmpeg -version \
    && ffprobe -version \
    && rm -rf /var/lib/apt/lists/*

# ─── Non-root user (required by Render / Koyeb security policies) ─────────────
RUN useradd -m -u 1000 botuser

# ─── App directory ────────────────────────────────────────────────────────────
WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create storage directories and set ownership
RUN mkdir -p storage/downloads storage/thumbnails storage/logs \
 && chown -R botuser:botuser /app

# Generate default background image
RUN python -c "\
from PIL import Image; \
img = Image.new('RGB', (1280, 720), color=(20, 20, 20)); \
img.save('storage/thumbnails/default_bg.jpg'); \
print('Default background created')" || echo "Skipping background image"

# ─── Runtime ─────────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

USER botuser

VOLUME ["/app/storage"]

CMD ["python", "app.py"]
