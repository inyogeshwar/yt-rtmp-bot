"""SQLite models using aiosqlite directly (no ORM overhead)."""
from __future__ import annotations

# Table creation SQL – executed once at startup
SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,   -- Telegram user ID
    username    TEXT,
    full_name   TEXT,
    role        TEXT DEFAULT 'user',   -- 'admin' | 'user' | 'banned'
    created_at  TEXT DEFAULT (datetime('now')),
    last_seen   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rtmp_configs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    rtmp_url    TEXT NOT NULL,
    stream_key  TEXT NOT NULL,
    label       TEXT DEFAULT 'default',
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS stream_sessions (
    id          TEXT PRIMARY KEY,       -- UUID
    user_id     INTEGER NOT NULL,
    title       TEXT,
    status      TEXT DEFAULT 'idle',    -- idle | running | paused | stopped | crashed
    rtmp_url    TEXT,
    stream_key  TEXT,
    quality     INTEGER DEFAULT 720,
    vbitrate    TEXT DEFAULT '2500k',
    abitrate    TEXT DEFAULT '128k',
    loop_mode   INTEGER DEFAULT 0,
    started_at  TEXT,
    stopped_at  TEXT,
    crash_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS playlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    title       TEXT,
    file_path   TEXT NOT NULL,
    duration    REAL,
    played      INTEGER DEFAULT 0,
    added_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES stream_sessions(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT,
    message     TEXT,
    user_id     INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""
