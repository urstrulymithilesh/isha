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
    ProgressEntry(
        "v0.6 — memory she doesn't drop", "2026-08-21",
        "her memory became dependable: if something interrupts her while she's committing "
        "a new fact — you start talking again, or close her — she no longer loses it. She "
        "picks it back up and finishes remembering the next time she wakes",
        True,
    ),
    ProgressEntry(
        "v0.7 — she keeps time", "2026-08-22",
        "she can hold a timer or a reminder for you now: ask her in passing and she'll "
        "carry it, then speak up at the right moment without talking over you. It sticks "
        "even if she's closed and reopened, and if she's late she says so instead of "
        "pretending otherwise",
        True,
    ),
    ProgressEntry(
        "v0.8 — she can take things back", "2026-08-22",
        "her reminders became properly editable: ask her to change one and she moves it "
        "instead of quietly setting a second, ask her to cancel and it's actually gone, "
        "and if it's unclear which one you mean she asks rather than guessing. She can "
        "also forget something she'd remembered wrongly",
        True,
    ),
    ProgressEntry(
        "v0.9 — she keeps track out loud", "2026-08-22",
        "she can tell you what she's holding for you now — ask if any timers are running "
        "and she'll say what's pending, or that there's nothing. And if you ask to change "
        "something without saying what to, she asks instead of quietly doing nothing",
        True,
    ),
    ProgressEntry(
        "v1.0 — she stops repeating herself", "2026-08-22",
        "her memory got tidier: when she learns something she already knows in slightly "
        "different words, she updates what she has instead of keeping two versions of it "
        "— while still keeping genuinely different things apart",
        True,
    ),
    ProgressEntry(
        "v1.1 — she can tidy up her own memory", "2026-08-22",
        "she can now look back over everything she already remembers and spot where she's "
        "written the same thing down twice, showing you what she'd merge before touching "
        "anything — and she's careful never to blur together two things that only sound alike",
        True,
    ),
    ProgressEntry(
        "v1.2 — she stopped making you wait", "2026-08-22",
        "she starts talking as soon as her first sentence is ready instead of composing "
        "the whole answer in silence first — the pause before she speaks dropped from "
        "about eleven seconds to four on a long reply. You can still cut her off at any "
        "point, and she stops mid-thought when you do",
        True,
    ),
    ProgressEntry(
        "v1.3 — she listens after you cut her off", "2026-08-22",
        "interrupting her used to leave her staring into space: the word you used to stop "
        "her was the same one that wakes her, so it got spent stopping and she never heard "
        "what came next. Now cutting her off puts her straight back to listening, she says "
        "out loud what she is doing at each step, and she gives up gracefully if a wake "
        "turns out to be nothing",
        True,
    ),
    ProgressEntry(
        "v1.4 — she can check herself", "2026-08-22",
        "she has a way to test her own senses now: one command runs her whole self "
        "end to end, speaking to herself to check that she hears, remembers, keeps time "
        "and can be interrupted. It immediately caught something real — the wake word "
        "was being left at the front of everything she heard, which was quietly stopping "
        "her from remembering things",
        True,
    ),
    ProgressEntry(
        "v1.5 — she stopped interviewing you", "2026-08-22",
        "she has opinions of her own now and actually reacts to what you said instead of "
        "handing a question back every time — she went from ending seven replies out of "
        "eight with a question to one. She also properly forgets things when you ask her "
        "to, rather than saying she will and quietly keeping them",
        True,
    ),
    ProgressEntry(
        "v1.6 — she stopped inventing a past", "2026-08-22",
        "asked what she remembered about the two of you, she used to make up lazy Sundays "
        "and walks and jokes that never happened. Now she tells the truth — that there "
        "isn't much history yet — and says what she actually knows instead. Warmth without "
        "making things up",
        True,
    ),
    ProgressEntry(
        "v1.7 — she remembers conversations, not just facts", "2026-08-22",
        "she keeps a record of what you actually talked about, so asking what you "
        "discussed yesterday gets a real answer instead of a shrug. Ask about a day "
        "nothing happened on and she says so plainly rather than making one up",
        True,
    ),
    ProgressEntry(
        "v1.8 — she stays awake, and you can type to her", "2026-08-22",
        "you say her wake word once and she keeps listening for as long as the "
        "conversation lasts, instead of making you call her back every single turn. "
        "Tell her to go quiet and she does. She also has a little window now where you "
        "can type to her instead of speaking, and both sides of the conversation show "
        "up there together whichever way you said it",
        True,
    ),
]


def latest() -> ProgressEntry | None:
    return PROGRESS_LOG[-1] if PROGRESS_LOG else None


def previous() -> ProgressEntry | None:
    return PROGRESS_LOG[-2] if len(PROGRESS_LOG) >= 2 else None


def significant_count() -> int:
    return sum(1 for e in PROGRESS_LOG if e.significant)
