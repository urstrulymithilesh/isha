"""Clean up a raw transcript before anything downstream reads it.

The pre-roll deliberately keeps audio from BEFORE the wake word fired, so the start of
a sentence spoken over the wake word isn't lost. The cost is that the wake word itself
usually lands in the transcript: "Jarvis. Set a timer for four seconds."

That prefix is not harmless. Measured on qwen2.5:3b, it silently breaks fact
extraction:

    "Jarvis. Remember that my favorite color is turquoise."  -> []          (nothing)
    "Remember that my favorite color is turquoise."          -> 1 fact      (correct)

So every turn was quietly handing the extractor a poisoned string. Stripping it is a
pure text operation, done once, before the transcript is used for anything.
"""

from __future__ import annotations

import re

# Filler that often precedes or surrounds the wake word in a transcript. The odd ones
# ("a", "they", "eight") are what whisper actually makes of a half-heard "hey": a live
# smoke run transcribed "hey jarvis" as "8 Jarvis", the junk prefix survived, and the
# action parser missed — whereupon she claimed "Photoshop opens." about nothing.
# Digits are handled in the loop for the same reason. All of these strip ONLY when a
# real wake token follows, so "they said hi" and "8 times 8" are untouched.
_FILLER = {"hey", "hi", "hello", "ok", "okay", "um", "uh", "so", "a", "hay",
           "they", "eight", "hate"}
_LEADING_PUNCT = re.compile(r"^[\s,.!?;:\-—]+")


def strip_wake_prefix(text: str, wake_model: str) -> str:
    """Remove a leading wake-word utterance ("hey_jarvis" -> "hey", "jarvis").

    Only strips from the FRONT, only wake tokens and filler, and never more than a
    handful of words — so "Jarvis, remind me to call Jarvis back" keeps the second one.
    """
    if not text or not text.strip():
        return text
    wake_tokens = {t.lower() for t in re.split(r"[_\s-]+", wake_model) if t}
    strippable = wake_tokens | _FILLER

    cursor = _LEADING_PUNCT.sub("", text)
    saw_wake_token = False
    consumed = 0
    limit = len(wake_tokens) + 2          # the wake words themselves, plus a filler or two
    while consumed < limit:
        match = re.match(r"([A-Za-z']+|\d+)", cursor)
        if not match:
            break
        word = match.group(1).lower()
        if word in wake_tokens:
            saw_wake_token = True
        elif not saw_wake_token and (word in _FILLER or word.isdigit()):
            pass                          # leading filler BEFORE the wake word ("hey ...")
        else:
            # Filler only counts ahead of the wake word. Past it, a word like "hello"
            # is what he actually said ("Hey Mycroft, hello").
            break
        cursor = _LEADING_PUNCT.sub("", cursor[match.end():])
        consumed += 1

    # Commit only if an actual WAKE token was there AND real content survives.
    # Without the first condition "hello world" would lose its "hello"; without the
    # second, a bare "Hey Jarvis." would be stripped to nothing and the turn dropped.
    if saw_wake_token and cursor.strip():
        return cursor
    return text
