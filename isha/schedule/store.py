"""Persisted timers and reminders — SQLite, absolute wall-clock fire times.

Why persisted (locked in the eng review): this runs on a laptop that sleeps. An
in-process timer's clock pauses with the machine, and a crash or restart loses
everything. Storing an absolute fire time means a 5pm reminder set at 2pm still
fires correctly whether the laptop slept 3-6pm or the app was closed and reopened.

Shares the same .db file as memory (one portable file), but its own table and its
own class — scheduling and memory are separate concerns.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PENDING, FIRED, DROPPED, CANCELLED = "pending", "fired", "dropped", "cancelled"


@dataclass(frozen=True)
class ScheduledItem:
    id: int
    task: str
    fire_at: datetime
    is_timer: bool


class SqliteScheduleStore:
    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS reminders(
                   id INTEGER PRIMARY KEY,
                   task TEXT NOT NULL,
                   fire_at TEXT NOT NULL,      -- ISO 8601, absolute wall-clock
                   is_timer INTEGER NOT NULL DEFAULT 0,
                   created_at TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'pending')"""
        )
        self._conn.commit()

    def add(self, task: str, fire_at: datetime, *, is_timer: bool = False) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders(task, fire_at, is_timer, created_at, status) "
            "VALUES(?, ?, ?, ?, ?)",
            (task, fire_at.isoformat(timespec="seconds"), int(is_timer),
             datetime.now().isoformat(timespec="seconds"), PENDING),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def pending(self) -> list[ScheduledItem]:
        """Everything still owed, soonest first — survives restart by definition."""
        rows = self._conn.execute(
            "SELECT id, task, fire_at, is_timer FROM reminders WHERE status = ? "
            "ORDER BY fire_at", (PENDING,)
        ).fetchall()
        return [
            ScheduledItem(id=r[0], task=r[1], fire_at=datetime.fromisoformat(r[2]),
                          is_timer=bool(r[3]))
            for r in rows
        ]

    def update_fire_at(self, item_id: int, fire_at: datetime) -> None:
        """Move an existing reminder instead of creating a second one."""
        self._conn.execute(
            "UPDATE reminders SET fire_at = ? WHERE id = ?",
            (fire_at.isoformat(timespec="seconds"), item_id),
        )
        self._conn.commit()

    def mark(self, item_id: int, status: str) -> None:
        self._conn.execute("UPDATE reminders SET status = ? WHERE id = ?", (status, item_id))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
