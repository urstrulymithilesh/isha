"""Parse the LLM's fact-extraction output into Facts.

Used in Phase 2 step 2 (the async idle-gap extractor), but the PARSING is a pure
function so it's fully unit-testable now. A 3B model produces messy output — this is
the confidence gate + malformed-output guard the eng review called for: it NEVER
raises and NEVER lets junk into memory. Bad JSON, wrong shape, missing text, or
low-confidence items are dropped; the caller gets a clean list[Fact].

Expected shape from the model: a JSON array of objects, e.g.
    [{"subject": "sister's name", "text": "the user's sister is named Anya",
      "confidence": 0.9}]
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from isha.core.interfaces import Fact


def _strip_code_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        if s[:4].lower() == "json":
            s = s[4:].strip()
    return s


def parse_extracted_facts(raw: str, *, min_confidence: float = 0.6) -> list[Fact]:
    """Best-effort parse. Returns [] on any malformed input; filters out items with
    no usable text or confidence below the gate."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        data = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        return []

    facts: list[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        conf = item.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            continue
        if conf < min_confidence:
            continue
        subject = item.get("subject")
        subject = subject.strip() if isinstance(subject, str) and subject.strip() else None
        facts.append(Fact(text=text.strip(), confidence=float(conf), subject=subject))
    return facts
