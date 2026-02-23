"""
Use FFprobe to analyse a media file and classify it.

Returns a MediaInfo dataclass with all relevant properties.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from config import FFPROBE_PATH


@dataclass
class StreamInfo:
    index: int
    codec_type: str          # 'video' | 'audio' | 'subtitle'
    codec_name: str
    width: Optional[int]     = None
    height: Optional[int]    = None
    fps: Optional[float]     = None
    duration: Optional[float]= None
    bitrate: Optional[int]   = None
    channels: Optional[int]  = None
    sample_rate: Optional[int] = None


@dataclass
class MediaInfo:
    path: Path
    duration: float          = 0.0
    size_bytes: int          = 0
    format_name: str         = ""
    streams: List[StreamInfo] = field(default_factory=list)

    # Derived
    has_video: bool          = False
    has_audio: bool          = False
    video_only: bool         = False
    audio_only: bool         = False

    # Video details
    width: Optional[int]     = None
    height: Optional[int]    = None
    fps: Optional[float]     = None
    video_codec: str         = ""

    # Audio details
    audio_codec: str         = ""
    channels: Optional[int]  = None
    sample_rate: Optional[int] = None

    # Classification
    media_type: str          = "unknown"  # video | audio | image | unknown


async def probe(path: str | Path) -> MediaInfo:
    """Run ffprobe and return a MediaInfo object."""
    path = Path(path)
    cmd = [
        FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFprobe error for {path}: {stderr.decode()}")

    data = json.loads(stdout.decode())

    # ── Parse format ─────────────────────────────────────────────────────────
    fmt = data.get("format", {})
    info = MediaInfo(
        path=path,
        duration=float(fmt.get("duration", 0)),
        size_bytes=int(fmt.get("size", 0)),
        format_name=fmt.get("format_name", ""),
    )

    # ── Parse streams ─────────────────────────────────────────────────────────
    for s in data.get("streams", []):
        codec_type = s.get("codec_type", "")
        fps_raw    = s.get("r_frame_rate", "0/1")
        fps_val: Optional[float] = None
        try:
            n, d = fps_raw.split("/")
            fps_val = float(n) / float(d) if float(d) else None
        except Exception:
            pass

        si = StreamInfo(
            index=s.get("index", 0),
            codec_type=codec_type,
            codec_name=s.get("codec_name", ""),
            width=s.get("width"),
            height=s.get("height"),
            fps=fps_val,
            duration=float(s.get("duration", info.duration or 0)),
            bitrate=int(s["bit_rate"]) if "bit_rate" in s else None,
            channels=s.get("channels"),
            sample_rate=int(s["sample_rate"]) if "sample_rate" in s else None,
        )
        info.streams.append(si)

        if codec_type == "video":
            info.has_video = True
            info.width      = si.width
            info.height     = si.height
            info.fps        = si.fps
            info.video_codec = si.codec_name
        elif codec_type == "audio":
            info.has_audio    = True
            info.audio_codec  = si.codec_name
            info.channels     = si.channels
            info.sample_rate  = si.sample_rate

    # ── Duration fallback from streams ────────────────────────────────────────
    if not info.duration:
        for s in info.streams:
            if s.duration and s.duration > info.duration:
                info.duration = s.duration

    # ── Classification ────────────────────────────────────────────────────────
    if info.has_video and info.has_audio:
        info.media_type  = "video"
    elif info.has_video and not info.has_audio:
        info.video_only  = True
        info.media_type  = "video_no_audio"
    elif info.has_audio and not info.has_video:
        info.audio_only  = True
        info.media_type  = "audio"
    else:
        info.media_type  = "unknown"

    return info


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"
