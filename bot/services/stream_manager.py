"""
Stream session manager.

Tracks all active FFmpeg processes in memory, maps them to DB session IDs,
handles crash detection and auto-restart.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from bot.database import db as _db
from bot.services import ffmpeg_service as _ff

logger = logging.getLogger(__name__)

MAX_AUTO_RESTARTS = 5


@dataclass
class Session:
    session_id: str
    user_id: int
    process: asyncio.subprocess.Process
    input_path: str
    rtmp_url: str
    stream_key: str
    quality: int
    vbitrate: str
    abitrate: str
    loop: bool
    playlist: Optional[List[str]] = None
    status: str = "running"          # running | paused | stopped
    restart_count: int = 0
    notify_cb: Optional[Callable]  = None   # async callback(session_id, msg)
    _monitor_task: Optional[asyncio.Task] = field(default=None, repr=False)


class StreamManager:
    """Singleton-style manager (instantiate once in main.py)."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    # ─── Public API ──────────────────────────────────────────────────────────

    async def start(
        self,
        session_id: str,
        user_id: int,
        input_path: str,
        rtmp_url: str,
        stream_key: str,
        quality: int = 720,
        vbitrate: str = "",
        abitrate: str = "128k",
        loop: bool = False,
        notify_cb: Optional[Callable] = None,
    ) -> Session:
        proc = await _ff.start_rtmp_stream(
            input_path=input_path,
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            quality=quality,
            vbitrate=vbitrate,
            abitrate=abitrate,
            loop=loop,
        )
        sess = Session(
            session_id=session_id,
            user_id=user_id,
            process=proc,
            input_path=input_path,
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            quality=quality,
            vbitrate=vbitrate,
            abitrate=abitrate,
            loop=loop,
            notify_cb=notify_cb,
        )
        self._sessions[session_id] = sess
        await _db.update_session_status(session_id, "running")
        sess._monitor_task = asyncio.create_task(self._monitor(sess))
        logger.info("Stream started: %s", session_id)
        return sess

    async def start_playlist(
        self,
        session_id: str,
        user_id: int,
        playlist: List[str],
        rtmp_url: str,
        stream_key: str,
        quality: int = 720,
        vbitrate: str = "",
        abitrate: str = "128k",
        loop: bool = False,
        notify_cb: Optional[Callable] = None,
    ) -> Session:
        proc = await _ff.start_playlist_stream(
            playlist=playlist,
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            quality=quality,
            vbitrate=vbitrate,
            abitrate=abitrate,
            loop=loop,
        )
        sess = Session(
            session_id=session_id,
            user_id=user_id,
            process=proc,
            input_path=";".join(playlist[:3]) + "...", # Summarized
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            quality=quality,
            vbitrate=vbitrate,
            abitrate=abitrate,
            loop=loop,
            playlist=playlist,
            notify_cb=notify_cb,
        )
        self._sessions[session_id] = sess
        await _db.update_session_status(session_id, "running")
        sess._monitor_task = asyncio.create_task(self._monitor(sess))
        logger.info("Playlist stream started: %s", session_id)
        return sess

    async def stop(self, session_id: str) -> bool:
        sess = self._sessions.get(session_id)
        if not sess:
            return False
        sess.status = "stopped"
        if sess._monitor_task:
            sess._monitor_task.cancel()
        try:
            sess.process.terminate()
            await asyncio.wait_for(sess.process.wait(), timeout=5)
        except Exception:
            try:
                sess.process.kill()
            except Exception:
                pass
        del self._sessions[session_id]
        await _db.update_session_status(session_id, "stopped")
        logger.info("Stream stopped: %s", session_id)
        return True

    async def pause(self, session_id: str) -> bool:
        """SIGSTOP on Unix / approximate on Windows."""
        import sys
        sess = self._sessions.get(session_id)
        if not sess or sess.status != "running":
            return False
        if sys.platform != "win32":
            import signal
            sess.process.send_signal(signal.SIGSTOP)
        sess.status = "paused"
        await _db.update_session_status(session_id, "paused")
        return True

    async def resume(self, session_id: str) -> bool:
        import sys
        sess = self._sessions.get(session_id)
        if not sess or sess.status != "paused":
            return False
        if sys.platform != "win32":
            import signal
            sess.process.send_signal(signal.SIGCONT)
        sess.status = "running"
        await _db.update_session_status(session_id, "running")
        return True

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def all_sessions(self) -> List[Session]:
        return list(self._sessions.values())

    def user_sessions(self, user_id: int) -> List[Session]:
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def status_text(self, session_id: str) -> str:
        sess = self._sessions.get(session_id)
        if not sess:
            return "❌ Not found"
        emoji = {"running": "🟢", "paused": "⏸️", "stopped": "🔴"}.get(sess.status, "❓")
        return (
            f"{emoji} Session: `{session_id[:8]}…`\n"
            f"Status : {sess.status}\n"
            f"Quality: {sess.quality}p  |  Vbitrate: {sess.vbitrate}\n"
            f"Loop   : {'yes' if sess.loop else 'no'}\n"
            f"Restarts: {sess.restart_count}/{MAX_AUTO_RESTARTS}"
        )

    # ─── Internal ────────────────────────────────────────────────────────────

    async def _monitor(self, sess: Session) -> None:
        """Watch the FFmpeg process and auto-restart on crash."""
        try:
            await sess.process.wait()
        except asyncio.CancelledError:
            return

        if sess.status == "stopped":
            return  # intentional stop

        logger.warning("Stream %s crashed (exit %s)", sess.session_id, sess.process.returncode)
        await _db.increment_crash(sess.session_id)
        sess.restart_count += 1

        if sess.restart_count > MAX_AUTO_RESTARTS:
            sess.status = "stopped"
            await _db.update_session_status(sess.session_id, "crashed")
            del self._sessions[sess.session_id]
            if sess.notify_cb:
                await sess.notify_cb(
                    sess.user_id,
                    f"🛑 Stream `{sess.session_id[:8]}` stopped after {MAX_AUTO_RESTARTS} crashes.",
                )
            return

        # Auto-restart
        if sess.notify_cb:
            await sess.notify_cb(
                sess.user_id,
                f"⚠️ Stream crashed. Auto-restarting ({sess.restart_count}/{MAX_AUTO_RESTARTS})…",
            )
        await asyncio.sleep(5)
        try:
            if sess.playlist:
                proc = await _ff.start_playlist_stream(
                    playlist=sess.playlist,
                    rtmp_url=sess.rtmp_url,
                    stream_key=sess.stream_key,
                    quality=sess.quality,
                    vbitrate=sess.vbitrate,
                    abitrate=sess.abitrate,
                    loop=sess.loop,
                )
            else:
                proc = await _ff.start_rtmp_stream(
                    input_path=sess.input_path,
                    rtmp_url=sess.rtmp_url,
                    stream_key=sess.stream_key,
                    quality=sess.quality,
                    vbitrate=sess.vbitrate,
                    abitrate=sess.abitrate,
                    loop=sess.loop,
                )
            sess.process = proc
            sess.status  = "running"
            await _db.update_session_status(sess.session_id, "running")
            sess._monitor_task = asyncio.create_task(self._monitor(sess))
        except Exception as exc:
            logger.error("Restart failed for %s: %s", sess.session_id, exc)
            sess.status = "stopped"
            await _db.update_session_status(sess.session_id, "crashed")
            del self._sessions[sess.session_id]


# ─── Global instance (import and use everywhere) ─────────────────────────────
stream_manager = StreamManager()
