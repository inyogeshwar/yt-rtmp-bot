"""Async database access layer (aiosqlite)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from config import DATABASE_PATH
from bot.database.models import SCHEMA


_DB: Optional[aiosqlite.Connection] = None


async def init_db() -> None:
    global _DB
    _DB = await aiosqlite.connect(str(DATABASE_PATH))
    _DB.row_factory = aiosqlite.Row
    await _DB.executescript(SCHEMA)
    await _DB.commit()


async def close_db() -> None:
    if _DB:
        await _DB.close()


def get_db() -> aiosqlite.Connection:
    assert _DB is not None, "Database not initialised – call init_db() first"
    return _DB


# ─── Users ───────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str) -> None:
    db = get_db()
    await db.execute(
        """INSERT INTO users (id, username, full_name)
           VALUES (:id, :username, :full_name)
           ON CONFLICT(id) DO UPDATE SET
               username  = excluded.username,
               full_name = excluded.full_name,
               last_seen = datetime('now')""",
        {"id": user_id, "username": username, "full_name": full_name},
    )
    await db.commit()


async def get_user(user_id: int) -> Optional[Dict]:
    db = get_db()
    async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def set_user_role(user_id: int, role: str) -> None:
    db = get_db()
    await db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    await db.commit()


# ─── RTMP ────────────────────────────────────────────────────────────────────

async def save_rtmp(user_id: int, rtmp_url: str, stream_key: str, label: str = "default") -> int:
    db = get_db()
    # upsert by (user_id, label)
    async with db.execute(
        "SELECT id FROM rtmp_configs WHERE user_id = ? AND label = ?", (user_id, label)
    ) as cur:
        row = await cur.fetchone()

    if row:
        await db.execute(
            "UPDATE rtmp_configs SET rtmp_url=?, stream_key=? WHERE id=?",
            (rtmp_url, stream_key, row["id"]),
        )
        rowid = row["id"]
    else:
        cur = await db.execute(
            "INSERT INTO rtmp_configs (user_id, rtmp_url, stream_key, label) VALUES (?,?,?,?)",
            (user_id, rtmp_url, stream_key, label),
        )
        rowid = cur.lastrowid  # type: ignore[assignment]
    await db.commit()
    return rowid  # type: ignore[return-value]


async def get_rtmp(user_id: int, label: str = "default") -> Optional[Dict]:
    db = get_db()
    async with db.execute(
        "SELECT * FROM rtmp_configs WHERE user_id = ? AND label = ?", (user_id, label)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ─── Stream Sessions ──────────────────────────────────────────────────────────

async def create_session(user_id: int, rtmp_url: str, stream_key: str, **kwargs) -> str:
    db = get_db()
    session_id = str(uuid.uuid4())
    quality    = kwargs.get("quality", 720)
    vbitrate   = kwargs.get("vbitrate", "2500k")
    abitrate   = kwargs.get("abitrate", "128k")
    loop_mode  = int(kwargs.get("loop_mode", False))
    title      = kwargs.get("title", "")
    await db.execute(
        """INSERT INTO stream_sessions
           (id, user_id, rtmp_url, stream_key, quality, vbitrate, abitrate, loop_mode, title)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, user_id, rtmp_url, stream_key, quality, vbitrate, abitrate, loop_mode, title),
    )
    await db.commit()
    return session_id


async def update_session_status(session_id: str, status: str) -> None:
    db = get_db()
    ts_field = "started_at" if status == "running" else "stopped_at" if status in ("stopped", "crashed") else None
    if ts_field:
        await db.execute(
            f"UPDATE stream_sessions SET status=?, {ts_field}=datetime('now') WHERE id=?",
            (status, session_id),
        )
    else:
        await db.execute("UPDATE stream_sessions SET status=? WHERE id=?", (status, session_id))
    await db.commit()


async def increment_crash(session_id: str) -> None:
    db = get_db()
    await db.execute(
        "UPDATE stream_sessions SET crash_count = crash_count + 1 WHERE id=?", (session_id,)
    )
    await db.commit()


async def get_session(session_id: str) -> Optional[Dict]:
    db = get_db()
    async with db.execute("SELECT * FROM stream_sessions WHERE id = ?", (session_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_user_sessions(user_id: int, active_only: bool = False) -> List[Dict]:
    db = get_db()
    if active_only:
        query = "SELECT * FROM stream_sessions WHERE user_id=? AND status IN ('running','paused')"
    else:
        query = "SELECT * FROM stream_sessions WHERE user_id=?"
    async with db.execute(query, (user_id,)) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ─── Playlist ─────────────────────────────────────────────────────────────────

async def playlist_add(session_id: str, file_path: str, title: str = "", duration: float = 0) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COALESCE(MAX(position),0)+1 FROM playlist WHERE session_id=?", (session_id,)
    ) as cur:
        pos = (await cur.fetchone())[0]
    cur2 = await db.execute(
        "INSERT INTO playlist (session_id, position, file_path, title, duration) VALUES (?,?,?,?,?)",
        (session_id, pos, file_path, title, duration),
    )
    await db.commit()
    return cur2.lastrowid  # type: ignore[return-value]


async def playlist_remove(item_id: int) -> None:
    db = get_db()
    await db.execute("DELETE FROM playlist WHERE id = ?", (item_id,))
    await db.commit()


async def playlist_list(session_id: str) -> List[Dict]:
    db = get_db()
    async with db.execute(
        "SELECT * FROM playlist WHERE session_id=? ORDER BY position", (session_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def playlist_clear(session_id: str) -> None:
    db = get_db()
    await db.execute("DELETE FROM playlist WHERE session_id=?", (session_id,))
    await db.commit()


async def playlist_next(session_id: str) -> Optional[Dict]:
    db = get_db()
    async with db.execute(
        "SELECT * FROM playlist WHERE session_id=? AND played=0 ORDER BY position LIMIT 1",
        (session_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def playlist_mark_played(item_id: int) -> None:
    db = get_db()
    await db.execute("UPDATE playlist SET played=1 WHERE id=?", (item_id,))
    await db.commit()


# ─── Settings ─────────────────────────────────────────────────────────────────

async def set_setting(key: str, value: str) -> None:
    db = get_db()
    await db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        (key, value),
    )
    await db.commit()


async def get_setting(key: str, default: str = "") -> str:
    db = get_db()
    async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else default


# ─── DB logs ─────────────────────────────────────────────────────────────────

async def db_log(level: str, message: str, user_id: Optional[int] = None) -> None:
    db = get_db()
    await db.execute(
        "INSERT INTO logs (level, message, user_id) VALUES (?,?,?)", (level, message, user_id)
    )
    await db.commit()
