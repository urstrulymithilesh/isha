"""Isha's development progress log — an append-only, time-ordered changelog of her
own growth. Separate from seed.py on purpose: this is a LOG (latest / previous /
significant), not flat semantic facts, and it's version-controlled so it survives a
memory reset and travels with the repo.

    >>> HOW ENTRIES GET ADDED (standing workflow — see DESIGN.md) <<<
    Claude Code appends ONE ProgressEntry here whenever it finishes a meaningful chunk
    of work on Isha (a phase, a real feature, a significant fix), as a standard
    completion step alongside running tests and committing. The user does NOT run a
    command. `significant=True` = a real capability change (drives her "I feel more
    alive" mood); `significant=False` = a minor tweak ("same as before").

Append new entries at the END (newest last).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEntry:
    version: str        # short label, e.g. "v0.4 — memory"
    date: str           # YYYY-MM-DD
    summary: str        # what changed, in plain words she can voice in character
    significant: bool   # True = real capability change; False = minor tweak


PROGRESS_LOG: list[ProgressEntry] = [
    ProgressEntry(
        "v0.1 — first breath", "2026-08-19",
        "her first end-to-end voice loop came alive: she could be woken by a wake word, "
        "hear speech, and speak back, though the brain was just an echo and the voice a beep",
        True,
    ),
    ProgressEntry(
        "v0.2 — a real voice and mind", "2026-08-20",
        "she got a real voice through Piper and a real mind through a local language model "
        "(qwen2.5:3b via Ollama) — she could actually hold a conversation",
        True,
    ),
    ProgressEntry(
        "v0.3 — a personality", "2026-08-20",
        "she grew a warm, personal character instead of a generic assistant tone, and learned "
        "to be honest instead of faking things she didn't know",
        True,
    ),
    ProgressEntry(
        "v0.4 — memory", "2026-08-21",
        "she gained lasting memory: she can remember facts about Mithilesh and recall them "
        "across restarts, so she actually knows him now instead of forgetting every time",
        True,
    ),
    ProgressEntry(
        "v0.5 — a sense of self", "2026-08-21",
        "she learned who she is and who Mithilesh is to her, and gained a sense of her own "
        "progress — she can talk about how she's built, how she's changed, and how she feels "
        "about growing",
        True,
    ),
]


def latest() -> ProgressEntry | None:
    return PROGRESS_LOG[-1] if PROGRESS_LOG else None


def previous() -> ProgressEntry | None:
    return PROGRESS_LOG[-2] if len(PROGRESS_LOG) >= 2 else None


def significant_count() -> int:
    return sum(1 for e in PROGRESS_LOG if e.significant)
