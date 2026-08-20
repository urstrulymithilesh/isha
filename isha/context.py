"""build_messages — assemble the LLM context under the strict read budget.

Order: persona (system) -> a "things you remember about them" line built from the
top-K recalled facts (system) -> the recent conversation turns (capped by count AND
chars) -> ending on the current user message. This is what makes Isha actually USE
what she stored, while keeping the prompt small enough for a 3B's 4096-token window.

Pure and deterministic, so it's unit-testable with no store/LLM.
"""

from __future__ import annotations

from collections.abc import Sequence

from isha.core.interfaces import Fact, Message


def _facts_line(facts: Sequence[Fact]) -> Message:
    joined = " | ".join(f.text for f in facts)
    return Message(
        "system",
        "You genuinely remember these things about the person you're talking to, from "
        "earlier conversations. Treat them as real memories — use them naturally and "
        "confidently, and state the details ACCURATELY (don't change a time or a name). "
        "Don't recite them as a list: " + joined,
    )


def build_messages(
    system_prompt: str,
    facts: Sequence[Fact],
    history: Sequence[Message],
    *,
    recent_limit: int,
    char_budget: int,
) -> list[Message]:
    """history should be the conversation turns ending with the CURRENT user message."""
    messages: list[Message] = []
    if system_prompt:
        messages.append(Message("system", system_prompt))
    if facts:
        messages.append(_facts_line(facts))

    tail = list(history[-recent_limit:]) if recent_limit else list(history)
    # Enforce the char budget by dropping the OLDEST tail turns, always keeping the
    # most recent (the current user message).
    while len(tail) > 1 and sum(len(m.content) for m in tail) > char_budget:
        tail.pop(0)
    messages.extend(tail)
    return messages
