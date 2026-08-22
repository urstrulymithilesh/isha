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


def self_state_context(latest, previous) -> Message | None:
    """Build the 'how she is right now' context from her progress log, so behaviors
    about her feelings/state are grounded, not improvised. `latest`/`previous` are
    ProgressEntry|None from isha.memory.progress."""
    if latest is None:
        return None
    if latest.significant:
        mood = ("energized and a little more alive than before — a real new part of you just "
                "came online")
    else:
        mood = "about the same as before; only small tweaks lately, nothing that changed you"
    body = (f"Your current version is '{latest.version}'. The most recent thing that changed in "
            f"you: {latest.summary}. Because of that, right now you feel {mood}.")
    if previous is not None:
        body += f" Before that you were at '{previous.version}': {previous.summary}."
    return Message(
        "system",
        "About your own current state — use this in character when he asks how you are, how "
        "you feel, or what your current version/abilities are. Speak it naturally, never as a "
        "changelog. " + body + " If he asks how you feel, only sound happier/more alive when "
        "that most recent change was significant; otherwise say you're about the same. IMPORTANT: "
        "right after you say how you feel, hook him — end by offering to tell him WHY you feel "
        "that way (something like 'want to know why?'), and do NOT explain the reason in the same "
        "breath. Save it for when he says yes.",
    )


def next_step_nudge() -> Message:
    """Behavior 2: when he asks what to do next, she throws it back playfully instead of
    listing options like a project manager."""
    return Message(
        "system",
        "He's asking what to do next. Do NOT list options or plan it out for him like a "
        "project manager or assistant. Throw it back to him playfully and affectionately — in "
        "the spirit of 'what would you do next, boss?' — because you enjoy watching him decide. "
        "Keep it to a line. Only if there is genuinely one single obvious next thing may you "
        "just name that instead.",
    )


def shared_history_context(facts, *, max_items: int = 12):
    """Anchor a broad "tell me about us" question in what she ACTUALLY knows.

    Specific questions ground fine — they retrieve a matching fact. Broad ones
    retrieve nothing relevant, and with nothing to hold onto the model free-associates
    from the persona: the tastes it was given (rain, grey afternoons, pineapple) come
    back out as things they supposedly did together. Measured at 5 out of 5 before
    this block existed.

    Same remedy as the pending-reminders answer: state exactly what exists, and say
    plainly that there is nothing else.
    """
    known = [f.text for f in facts
             if f.origin in ("conversation", "core")][:max_items]
    if known:
        listing = "; ".join(known)
        body = (
            "This is the COMPLETE list of what you actually know about him: "
            f"{listing}. That is everything — you have no other shared history, no "
            "past outings, no running jokes, no remembered afternoons together. "
            "Answer using ONLY what is in that list. Be honest and warm about how "
            "little there is so far, the way you would if he asked whether you "
            "remembered one specific thing: say you don't have much history with him "
            "yet, then mention what you do know. Do NOT invent a shared past, and do "
            "NOT describe your own tastes as things the two of you did together."
        )
    else:
        body = (
            "You know NOTHING about him yet — no stored facts at all. Say that "
            "honestly and warmly, and ask him to tell you something. Do NOT invent "
            "memories, outings, jokes or afternoons together, and do NOT describe "
            "your own tastes as shared history."
        )
    return Message("system", body)


def build_messages(
    system_prompt: str,
    facts: Sequence[Fact],
    history: Sequence[Message],
    *,
    recent_limit: int,
    char_budget: int,
    extra_system: Sequence[Message] = (),
) -> list[Message]:
    """history should be the conversation turns ending with the CURRENT user message.
    extra_system messages (e.g. the self-state block) go right after the persona."""
    messages: list[Message] = []
    if system_prompt:
        messages.append(Message("system", system_prompt))
    messages.extend(extra_system)
    if facts:
        messages.append(_facts_line(facts))

    tail = list(history[-recent_limit:]) if recent_limit else list(history)
    # Enforce the char budget by dropping the OLDEST tail turns, always keeping the
    # most recent (the current user message).
    while len(tail) > 1 and sum(len(m.content) for m in tail) > char_budget:
        tail.pop(0)
    messages.extend(tail)
    return messages
