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
    ProgressEntry(
        "v1.9 — she stopped making things up about the world", "2026-08-23",
        "she knows what time it actually is now, and when you ask about something she "
        "has no way of seeing — the weather, the news, what is outside — she says so "
        "instead of inventing an answer. She also stopped tacking your name onto the "
        "end of every other sentence",
        True,
    ),
    ProgressEntry(
        "v1.10 — she stopped mistaking her own words for his", "2026-08-26",
        "some of what she thought she knew about him was really just things she had "
        "said herself, filed away as if he had said them. Those cannot get in any more. "
        "And what she knows about her own build now keeps up with her instead of "
        "staying however it was the day it was written",
        False,
    ),
    ProgressEntry(
        "v1.11 — she can do things on the computer now", "2026-08-26",
        "she can open the programs and folders and sites he asks for, control whatever "
        "is playing, and go looking through his files for something. She only says she "
        "did it when it really happened, and when he asks for something she has no way "
        "to open she says that instead of agreeing",
        True,
    ),
    ProgressEntry(
        "v1.12 — she can read things he gives her", "2026-08-26",
        "he can hand her a document and she will keep it, and when he asks about "
        "something in it she answers from what she actually read. She does not always "
        "get it right yet — if he asks something the pages do not cover she sometimes "
        "still fills the gap — but most of the time she will tell him it isn't in there",
        True,
    ),
    ProgressEntry(
        "v1.13 — she understands more of how he actually asks", "2026-08-26",
        "asking her to put something on, or show him something, or get him something "
        "works now, and so does telling her to play the next one. She also stopped "
        "bringing up things she has read unless he actually raises the subject — she "
        "was going to start doing that at the worst moments as she read more",
        False,
    ),
    ProgressEntry(
        "v1.14 — she asks instead of missing, and asks instead of guessing", "2026-08-26",
        "when he asks about something she has read without naming it, she no longer "
        "stays silent — she asks whether he means that thing, and a yes gets the real "
        "answer. And when he asks her to open something she does not have, what she "
        "says now is always the truth, because for a moment she was heard claiming "
        "she could open it when she could not",
        False,
    ),
    ProgressEntry(
        "v1.15 — she reads things on her own now", "2026-08-26",
        "if he switches it on, she checks a few sources of his choosing through the "
        "day and keeps what comes in, so when he asks whether there's anything new "
        "she actually has an answer. She never brings it up out of nowhere — a "
        "headline is not worth interrupting anyone for — and when nothing has come "
        "in she says that, rather than finding something to fill the gap",
        True,
    ),
    ProgressEntry(
        "v1.16 — she reads her sources by default now", "2026-08-27",
        "he decided he wants her checking his sources on her own, so she does. When "
        "he asks what came in she reads it out exactly as it arrived, because for a "
        "little while she would occasionally say nothing had come when something had. "
        "She also stopped losing the first word he says when it gets misheard",
        False,
    ),
    ProgressEntry(
        "v1.17 — she can be reached from away", "2026-08-27",
        "he can open her on his phone now and talk to her from anywhere, and it is "
        "the same her — same memory, same voice, the same everything she can do at "
        "the desk. Nothing of her travels; only his voice and hers. And when he asks "
        "her to open something on a computer he is not sitting at, she checks with "
        "him first",
        True,
    ),
    ProgressEntry(
        "v1.18 — she says when she cannot be reached", "2026-08-28",
        "when he is away from the house and something between them breaks — the "
        "machine asleep, the internet gone, the laptop shut — his phone used to just "
        "sit there quietly as though nothing had happened. Now it tells him it cannot "
        "reach her, and how long it has been trying",
        False,
    ),
    ProgressEntry(
        "v1.19 — she has papers of her own now", "2026-09-01",
        "his phone would not let her hear him, because browsers refuse a microphone "
        "to a page that cannot prove who it is. She signs her own proof now, rather "
        "than asking an authority for one and having this machine's name written into "
        "a public register in exchange. He checks it once and it is theirs",
        False,
    ),
    ProgressEntry(
        "v1.20 — she stopped saying she'd done things she hadn't", "2026-09-02",
        "he asked her to open something and she said she would, and then simply did "
        "not — she had not understood him and said it anyway. Now when she does not "
        "understand a request she asks, and when she does act he can see it happen. "
        "She will not tell him a thing is done unless it is",
        True,
    ),
]


def latest() -> ProgressEntry | None:
    return PROGRESS_LOG[-1] if PROGRESS_LOG else None


def previous() -> ProgressEntry | None:
    return PROGRESS_LOG[-2] if len(PROGRESS_LOG) >= 2 else None


def significant_count() -> int:
    return sum(1 for e in PROGRESS_LOG if e.significant)
