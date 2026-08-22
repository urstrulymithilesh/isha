"""Scheduler — decides what's due, what's too late to matter, and fires it.

The DECISION is a pure function (`triage`) so every rule is unit-testable with a
fake clock and no db, no audio, no model. The async loop around it is a thin tick
that hands announcements to a callback — in practice `Orchestrator.notify`, which
owns *when* it's actually spoken (never mid-utterance).

Reconcile-on-wake: because fire times are absolute and stored, startup and every
tick use the same code path. A reminder that came due while the laptop slept or
the app was closed simply looks "overdue" on the next tick and fires with an
honest late note — unless it's so old that announcing it would be noise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from isha.schedule.parse import announcement
from isha.schedule.store import DROPPED, FIRED, ScheduledItem, SqliteScheduleStore


def triage(
    items: list[ScheduledItem],
    *,
    now: datetime,
    stale_after_s: float,
    overdue_note_after_s: float,
) -> tuple[list[tuple[ScheduledItem, str]], list[ScheduledItem]]:
    """Pure. -> (to_fire as (item, spoken_text), to_drop).

    Anything at or past its fire time fires. If it's more than
    `overdue_note_after_s` late, the announcement admits how late it is. If it's
    more than `stale_after_s` late, it's dropped instead — waking someone at
    midnight for a 5pm gym reminder is worse than staying quiet.
    """
    to_fire: list[tuple[ScheduledItem, str]] = []
    to_drop: list[ScheduledItem] = []
    for item in items:
        late = (now - item.fire_at).total_seconds()
        if late < 0:
            continue                                   # not due yet
        if late > stale_after_s:
            to_drop.append(item)
            continue
        note_late = late if late > overdue_note_after_s else 0.0
        to_fire.append((item, announcement(item.task, is_timer=item.is_timer,
                                           overdue_seconds=note_late)))
    return to_fire, to_drop


class Scheduler:
    def __init__(
        self,
        store: SqliteScheduleStore,
        notify: Callable[[str], None],
        *,
        tick_seconds: float = 2.0,
        stale_after_s: float = 2 * 3600,
        overdue_note_after_s: float = 60.0,
    ) -> None:
        self._store = store
        self._notify = notify
        self._tick = tick_seconds
        self._stale_after_s = stale_after_s
        self._overdue_note_after_s = overdue_note_after_s

    def add(self, task: str, fire_at: datetime, *, is_timer: bool = False) -> int:
        return self._store.add(task, fire_at, is_timer=is_timer)

    def check(self, *, now: datetime | None = None) -> int:
        """One reconcile pass: fire what's due, drop what's stale. Returns fired count.
        Used identically at startup and on every tick — that IS the reconcile."""
        now = now or datetime.now()
        to_fire, to_drop = triage(
            self._store.pending(), now=now,
            stale_after_s=self._stale_after_s,
            overdue_note_after_s=self._overdue_note_after_s,
        )
        for item in to_drop:
            self._store.mark(item.id, DROPPED)
            print(f"  [reminder] dropped as too old to be useful: {item.task or 'timer'}")
        for item, spoken in to_fire:
            self._store.mark(item.id, FIRED)   # mark BEFORE notifying: never fire twice
            print(f"  [reminder] firing: {spoken}")
            self._notify(spoken)
        return len(to_fire)

    async def run(self) -> None:
        """Tick forever. The first pass is the startup/resume reconcile."""
        while True:
            try:
                self.check()
            except Exception as e:  # noqa: BLE001 - a bad reminder must not kill the loop
                print(f"  [reminder] check failed: {type(e).__name__}: {e}")
            await asyncio.sleep(self._tick)
