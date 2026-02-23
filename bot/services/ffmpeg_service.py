"""
FFmpeg processing service.

Provides async helpers for:
- Video conversion / re-encoding
- Audio extraction
- Stream-ready output (pipe to RTMP)
- Background-image + audio → video
- Thumbnail overlay / watermark
- Speed / resolution / loop options
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional

from config import (
    FFMPEG_PATH,
    DEFAULT_BG_IMAGE,
    DEFAULT_FPS,
    QUALITY_MAP,
    DOWNLOADS_PATH,
)

logger = logging.getLogger(__name__)


def _build_rtmp_url(rtmp_url: str, stream_key: str) -> str:
    base = rtmp_url.rstrip("/")
    return f"{base}/{stream_key}" if stream_key else base


# ─── Low-level async runner ───────────────────────────────────────────────────

async def run_ffmpeg(args: List[str]) -> asyncio.subprocess.Process:
    """Start an ffmpeg process and return it (caller manages it)."""
    cmd = [FFMPEG_PATH, "-hide_banner", "-loglevel", "warning"] + args
    logger.debug("FFmpeg command: %s", " ".join(shlex.quote(a) for a in cmd))
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def run_ffmpeg_and_wait(args: List[str]) -> tuple[int, str]:
    """Run ffmpeg, wait for completion, return (returncode, stderr)."""
    proc = await run_ffmpeg(args)
    _, stderr = await proc.communicate()
    return proc.returncode, stderr.decode(errors="replace")


# ─── Conversion helpers ───────────────────────────────────────────────────────

async def convert_to_mp3(input_path: str, output_path: Optional[str] = None) -> Path:
    """Extract / convert audio to MP3."""
    inp = Path(input_path)
    out = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + ".mp3")
    args = [
        "-y", "-i", str(inp),
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"MP3 conversion failed: {err}")
    return out


async def convert_to_mp4(
    input_path: str,
    output_path: Optional[str] = None,
    quality: int = 720,
    vbitrate: str = "",
    fps: int = DEFAULT_FPS,
) -> Path:
    """Re-encode a video file to H.264/AAC MP4."""
    inp = Path(input_path)
    qi  = QUALITY_MAP.get(quality, QUALITY_MAP[720])
    vb  = vbitrate or qi["vbitrate"]
    res = qi["resolution"]
    out = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + f"_{quality}p.mp4")
    args = [
        "-y", "-i", str(inp),
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", vb,
        "-vf", f"scale={res},fps={fps}",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"MP4 conversion failed: {err}")
    return out


async def audio_to_video(
    audio_path: str,
    bg_image: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Path:
    """Combine a static image with an audio track → MP4 suitable for streaming."""
    inp  = Path(audio_path)
    bg   = str(bg_image or DEFAULT_BG_IMAGE)
    out  = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + "_video.mp4")
    args = [
        "-y",
        "-loop", "1", "-i", bg,
        "-i", str(inp),
        "-c:v", "libx264", "-preset", "veryfast",
        "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"Audio→video conversion failed: {err}")
    return out


async def extract_thumbnail(input_path: str, output_path: Optional[str] = None, ts: float = 5.0) -> Path:
    inp = Path(input_path)
    out = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + "_thumb.jpg")
    args = [
        "-y", "-ss", str(ts), "-i", str(inp),
        "-frames:v", "1",
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"Thumbnail extraction failed: {err}")
    return out


async def add_watermark(
    video_path: str,
    watermark_path: str,
    output_path: Optional[str] = None,
    position: str = "10:10",
) -> Path:
    inp   = Path(video_path)
    wm    = Path(watermark_path)
    out   = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + "_wm.mp4")
    args  = [
        "-y", "-i", str(inp), "-i", str(wm),
        "-filter_complex", f"overlay={position}",
        "-c:a", "copy",
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"Watermark failed: {err}")
    return out


async def change_speed(video_path: str, speed: float, output_path: Optional[str] = None) -> Path:
    """Change playback speed (0.5 = half speed, 2.0 = double speed)."""
    inp = Path(video_path)
    out = Path(output_path) if output_path else DOWNLOADS_PATH / (inp.stem + f"_x{speed}.mp4")
    vf  = f"setpts={1/speed:.4f}*PTS"
    af  = f"atempo={speed:.2f}"
    args = [
        "-y", "-i", str(inp),
        "-vf", vf,
        "-af", af,
        str(out),
    ]
    rc, err = await run_ffmpeg_and_wait(args)
    if rc != 0:
        raise RuntimeError(f"Speed change failed: {err}")
    return out


# ─── RTMP streaming processes ─────────────────────────────────────────────────

def build_stream_args(
    input_path: str,
    rtmp_url: str,
    stream_key: str,
    quality: int = 720,
    vbitrate: str = "",
    abitrate: str = "128k",
    loop: bool = False,
    fps: int = DEFAULT_FPS,
) -> List[str]:
    """Build the ffmpeg argument list for an RTMP push (does NOT start process)."""
    qi    = QUALITY_MAP.get(quality, QUALITY_MAP[720])
    vb    = vbitrate or qi["vbitrate"]
    res   = qi["resolution"]
    dest  = _build_rtmp_url(rtmp_url, stream_key)
    loop_args = ["-stream_loop", "-1"] if loop else []
    args = (
        loop_args
        + ["-re", "-i", str(input_path)]
        + [
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", vb,
            "-vf", f"scale={res},fps={fps}",
            "-c:a", "aac", "-b:a", abitrate,
            "-f", "flv",
            dest,
        ]
    )
    return args


async def start_rtmp_stream(
    input_path: str,
    rtmp_url: str,
    stream_key: str,
    quality: int = 720,
    vbitrate: str = "",
    abitrate: str = "128k",
    loop: bool = False,
) -> asyncio.subprocess.Process:
    """Start an RTMP stream; returns the running process."""
    args = build_stream_args(input_path, rtmp_url, stream_key, quality, vbitrate, abitrate, loop)
    return await run_ffmpeg(args)


async def start_playlist_stream(
    playlist: List[str],
    rtmp_url: str,
    stream_key: str,
    quality: int = 720,
    vbitrate: str = "",
    abitrate: str = "128k",
    loop: bool = False,
) -> asyncio.subprocess.Process:
    """Stream a list of files sequentially using ffmpeg concat demuxer."""
    # Write a concat list file
    concat_file = DOWNLOADS_PATH / "concat_list.txt"
    content = "\n".join(f"file '{p}'" for p in playlist)
    concat_file.write_text(content)

    qi    = QUALITY_MAP.get(quality, QUALITY_MAP[720])
    vb    = vbitrate or qi["vbitrate"]
    res   = qi["resolution"]
    dest  = _build_rtmp_url(rtmp_url, stream_key)
    loop_flag = ["-stream_loop", "-1"] if loop else []

    args = (
        loop_flag
        + ["-re", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        + [
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", vb,
            "-vf", f"scale={res}",
            "-c:a", "aac", "-b:a", abitrate,
            "-f", "flv",
            dest,
        ]
    )
    return await run_ffmpeg(args)
