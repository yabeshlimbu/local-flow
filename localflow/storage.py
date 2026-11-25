"""SQLite history of dictations and Notetaker meetings."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from .config import DB_PATH

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS dictations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created REAL NOT NULL,
                mode TEXT NOT NULL,           -- dictation | command
                app TEXT, app_name TEXT,
                raw TEXT, final TEXT,
                instruction TEXT,
                language TEXT,
                duration REAL, words INTEGER, latency REAL
            );
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created REAL NOT NULL,
                title TEXT, duration REAL,
                transcript TEXT, summary TEXT, notes TEXT,
                audio_path TEXT, embedding TEXT
            );
            """
        )


def add_dictation(**row) -> int:
    row.setdefault("created", time.time())
    row["words"] = len((row.get("final") or "").split())
    cols = ",".join(row)
    q = ",".join("?" for _ in row)
    with _lock, _conn() as c:
        cur = c.execute(f"INSERT INTO dictations ({cols}) VALUES ({q})", list(row.values()))
        return cur.lastrowid


def list_dictations(limit: int = 200, search: str = "") -> list[dict]:
    with _lock, _conn() as c:
        if search:
            rows = c.execute(
                "SELECT * FROM dictations WHERE final LIKE ? OR raw LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM dictations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def last_dictation() -> dict | None:
    rows = list_dictations(1)
    return rows[0] if rows else None


def delete_dictation(row_id: int) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM dictations WHERE id=?", (row_id,))


def clear_dictations() -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM dictations")


def stats() -> dict:
    now = time.time()
    week = now - 7 * 86400
    with _lock, _conn() as c:
        total = c.execute("SELECT COUNT(*), COALESCE(SUM(words),0), COALESCE(SUM(duration),0) FROM dictations").fetchone()
        wk = c.execute("SELECT COUNT(*), COALESCE(SUM(words),0) FROM dictations WHERE created>?", (week,)).fetchone()
        days = c.execute(
            "SELECT date(created,'unixepoch','localtime') d, SUM(words) w FROM dictations "
            "WHERE created>? GROUP BY d ORDER BY d", (now - 30 * 86400,)).fetchall()
        apps = c.execute(
            "SELECT COALESCE(app_name,'?') a, SUM(words) w FROM dictations GROUP BY a ORDER BY w DESC LIMIT 8").fetchall()
        lat = c.execute("SELECT AVG(latency) FROM (SELECT latency FROM dictations ORDER BY id DESC LIMIT 50)").fetchone()
    minutes = total[2] / 60 if total[2] else 0
    days_set = {r["d"] for r in days}
    streak = 0
    t = now
    while time.strftime("%Y-%m-%d", time.localtime(t)) in days_set:
        streak += 1
        t -= 86400
    return {
        "count": total[0], "words": total[1],
        "wpm": round(total[1] / minutes) if minutes > 0.05 else 0,
        "week_count": wk[0], "week_words": wk[1],
        # typing at ~40 wpm vs speaking: minutes saved
        "minutes_saved": round(max(0, total[1] / 40 - minutes)),
        "streak": streak,
        "avg_latency": round(lat[0] or 0, 2),
        "daily": [dict(r) for r in days],
        "apps": [dict(r) for r in apps],
    }


# --- meetings ---------------------------------------------------------------

def add_meeting(**row) -> int:
    row.setdefault("created", time.time())
    if isinstance(row.get("embedding"), list):
        row["embedding"] = json.dumps(row["embedding"])
    cols = ",".join(row)
    q = ",".join("?" for _ in row)
    with _lock, _conn() as c:
        return c.execute(f"INSERT INTO meetings ({cols}) VALUES ({q})", list(row.values())).lastrowid


def update_meeting(mid: int, **fields) -> None:
    if isinstance(fields.get("embedding"), list):
        fields["embedding"] = json.dumps(fields["embedding"])
    sets = ",".join(f"{k}=?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE meetings SET {sets} WHERE id=?", [*fields.values(), mid])


def list_meetings() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, created, title, duration, summary, notes FROM meetings ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_meeting(mid: int) -> dict | None:
    with _lock, _conn() as c:
        r = c.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def all_meetings_full() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM meetings ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def delete_meeting(mid: int) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM meetings WHERE id=?", (mid,))
