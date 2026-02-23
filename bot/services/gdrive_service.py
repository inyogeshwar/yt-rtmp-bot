"""
Google Drive download service.

Supports:
- Direct public share links  (no auth)
- Service-account / OAuth downloads via google-api-python-client (optional)
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from config import DOWNLOADS_PATH

logger = logging.getLogger(__name__)

_GDRIVE_DIRECT_URL = "https://drive.google.com/uc?export=download&id={file_id}"
_GDRIVE_CONFIRM_RE = re.compile(r'confirm=([0-9A-Za-z_\-]+)')


def extract_file_id(url: str) -> Optional[str]:
    """Extract the Google Drive file ID from various URL formats."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_\-]+)",
        r"id=([a-zA-Z0-9_\-]+)",
        r"/d/([a-zA-Z0-9_\-]+)/",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


async def download_gdrive(
    url: str,
    progress_cb: Optional[Callable] = None,
    filename: Optional[str] = None,
) -> Optional[Path]:
    """Download a publicly shared Google Drive file."""
    file_id = extract_file_id(url)
    if not file_id:
        logger.error("Could not extract GDrive file ID from: %s", url)
        return None

    direct_url = _GDRIVE_DIRECT_URL.format(file_id=file_id)
    output_path = DOWNLOADS_PATH / (filename or f"gdrive_{file_id}")

    async with aiohttp.ClientSession() as session:
        async with session.get(direct_url, allow_redirects=True) as resp:
            # Handle large-file virus scan warning page
            if "text/html" in resp.content_type:
                html = await resp.text()
                confirm_match = _GDRIVE_CONFIRM_RE.search(html)
                if confirm_match:
                    confirm_token = confirm_match.group(1)
                    download_url = (
                        f"https://drive.google.com/uc?export=download"
                        f"&id={file_id}&confirm={confirm_token}"
                    )
                    async with session.get(download_url, allow_redirects=True) as resp2:
                        return await _write_response(resp2, output_path, progress_cb)
                else:
                    logger.error("GDrive returned HTML – file may not be publicly accessible.")
                    return None
            return await _write_response(resp, output_path, progress_cb)


async def _write_response(
    resp: aiohttp.ClientResponse,
    output_path: Path,
    progress_cb: Optional[Callable],
) -> Path:
    content_disp = resp.headers.get("Content-Disposition", "")
    # Try to derive extension from Content-Disposition
    fn_match = re.search(r'filename="?([^";]+)"?', content_disp)
    if fn_match:
        original_name = fn_match.group(1).strip()
        ext = Path(original_name).suffix
        if ext and not output_path.suffix:
            output_path = output_path.with_suffix(ext)

    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 1024 * 512  # 512 KB

    with open(output_path, "wb") as f:
        async for chunk in resp.content.iter_chunked(chunk_size):
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total:
                pct = int(downloaded / total * 100)
                if pct % 10 == 0:
                    progress_cb(f"⬇️ GDrive: {pct}% ({downloaded // (1024*1024)} MB)")

    logger.info("GDrive download complete: %s", output_path)
    return output_path
