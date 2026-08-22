"""Turn "remind me to stretch in 20 minutes" into a concrete fire time.

Deliberately deterministic (regex + datetime), NOT an LLM call. Three reasons:
every extra LLM round-trip costs 3-7s on this CPU-bound setup; a 3B's structured
output is exactly what proved unreliable for fact grounding; and timer phrasings
are a small closed set. No match simply means "this was ordinary conversation",
so nothing breaks when someone says something unexpected.

Pure functions only — fully testable with a fake `now`, no clock, no db, no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# "in 10 minutes", "in an hour", "in half an hour", "for 30 seconds"
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60,
}
_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}

_RELATIVE = re.compile(
    r"\b(?:in|after|for)\s+"
    r"(?P<half>half\s+(?:an?\s+)?)?"
    r"(?P<qty>\d+|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")?\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
    re.I,
)

# "at 5pm", "at 5:30 pm", "at 17:00"
_ABSOLUTE = re.compile(
    r"\bat\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm|a\.m\.|p\.m\.)?\b",
    re.I,
)

# Phrases that mean "this is a scheduling request", stripped to leave the task.
_TRIGGERS = (
    "could you remind me to", "can you remind me to", "please remind me to",
    "remind me to", "remind me", "set a timer for", "set a timer", "start a timer for",
    "start a timer", "set an alarm for", "set an alarm", "wake me up", "wake me",
    "give me a nudge to", "nudge me to", "ping me to", "tell me to", "let me know to",
)
_TIMER_WORDS = ("timer", "alarm")


@dataclass(frozen=True)
class ScheduleRequest:
    task: str            # what to say when it fires ("" for a bare timer)
    fire_at: datetime    # absolute wall-clock target
    is_timer: bool       # a countdown ("timer for 10 min") vs a reminder ("at 5pm")
    spoken_delay: str    # human phrasing of the wait, for her confirmation


def _quantity(m: re.Match) -> float | None:
    if m.group("half"):
        return 0.5
    raw = m.group("qty")
    if raw is None:
        return None
    if raw.isdigit():
        return float(raw)
    return float(_WORD_NUMBERS.get(raw.lower(), 0)) or None


def _unit_seconds(unit: str) -> int:
    u = unit.lower().rstrip("s")
    return _UNIT_SECONDS.get(u, 60)


def _clean_task(text: str, *, spans: list[tuple[int, int]]) -> str:
    """Remove the time expression, then the trigger phrase, leaving the task."""
    out = text
    for start, end in sorted(spans, reverse=True):
        out = out[:start] + " " + out[end:]
    low = out.lower()
    for trig in _TRIGGERS:                      # longest-first via _TRIGGERS ordering
        idx = low.find(trig)
        if idx != -1:
            out = out[:idx] + " " + out[idx + len(trig):]
            low = out.lower()
            break
    out = re.sub(r"^\s*(?:to|for|that|about)\b", " ", out.strip(), flags=re.I)
    out = re.sub(r"\b(?:please|hey|isha|ok|okay)\b", " ", out, flags=re.I)
    out = re.sub(r"[\s,.!?]+", " ", out).strip(" ,.!?")
    return out


def _phrase_delay(seconds: float) -> str:
    if seconds < 90:
        return f"{int(round(seconds))} seconds"
    minutes = seconds / 60
    if minutes < 90:
        n = int(round(minutes))
        return "a minute" if n == 1 else f"{n} minutes"
    hours = minutes / 60
    n = round(hours * 2) / 2
    return "an hour" if n == 1 else f"{n:g} hours"


def parse_schedule_request(text: str, *, now: datetime) -> ScheduleRequest | None:
    """Return a ScheduleRequest if `text` asks for a timer/reminder, else None."""
    if not text or not text.strip():
        return None
    low = text.lower()

    rel = _RELATIVE.search(text)
    qty = _quantity(rel) if rel else None
    if rel is not None and qty:
        seconds = qty * _unit_seconds(rel.group("unit"))
        fire_at = now + timedelta(seconds=seconds)
        task = _clean_task(text, spans=[rel.span()])
        is_timer = any(w in low for w in _TIMER_WORDS) or not task
        return ScheduleRequest(task, fire_at, is_timer, _phrase_delay(seconds))

    absol = _ABSOLUTE.search(text)
    if absol is not None:
        # Only treat "at 5" as scheduling if the sentence actually asks for one.
        if not any(t in low for t in _TRIGGERS):
            return None
        hour = int(absol.group("hour"))
        minute = int(absol.group("minute") or 0)
        mer = (absol.group("meridiem") or "").replace(".", "").lower()
        if mer == "pm" and hour < 12:
            hour += 12
        elif mer == "am" and hour == 12:
            hour = 0
        elif not mer and hour < 8:
            hour += 12          # bare "at 5" almost always means this afternoon/evening
        if hour > 23 or minute > 59:
            return None
        fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if fire_at <= now:
            fire_at += timedelta(days=1)        # already passed today -> tomorrow
        task = _clean_task(text, spans=[absol.span()])
        delay = _phrase_delay((fire_at - now).total_seconds())
        return ScheduleRequest(task, fire_at, False, delay)

    return None


def announcement(task: str, *, is_timer: bool, overdue_seconds: float = 0.0) -> str:
    """What she should say when it fires — with an honest late note if overdue."""
    if is_timer or not task:
        body = "your timer is up"
    else:
        body = f"time to {task}" if not task.lower().startswith("time") else task
    if overdue_seconds > 0:
        body += f" — this was due {_phrase_delay(overdue_seconds)} ago, sorry"
    return body
