"""Memory tests: store / dedupe / recall / read-budget / conflict / persistence,
plus extraction-output rejection. All with a fake deterministic embedder and an
in-memory (or tmp-file) SQLite — no fastembed model, no mic, no LLM.
"""

from isha.core.interfaces import Fact, Message
from isha.memory.extraction import parse_extracted_facts
from isha.memory.store import SqliteMemoryStore


class FakeEmbedder:
    """Deterministic keyword embedding so recall is predictable in tests.
    Topic dims: [sister, drink, gym, bias]. Same topic -> near vector."""

    def _vec(self, t: str) -> list[float]:
        t = t.lower()
        return [
            1.0 if "sister" in t else 0.0,
            1.0 if ("coffee" in t or "tea" in t or "drink" in t) else 0.0,
            1.0 if ("gym" in t or "workout" in t) else 0.0,
            1.0,  # bias keeps every vector non-zero
        ]

    def embed(self, texts):
        return [self._vec(t) for t in texts]


def _store(tmp_path=None, log=None):
    db = str(tmp_path / "mem.db") if tmp_path else ":memory:"
    return SqliteMemoryStore(db, FakeEmbedder(), log_path=log)


# -- store + recall ---------------------------------------------------------


def test_store_and_semantic_recall():
    s = _store()
    s.add_fact(Fact(text="the user's sister is named Anya", confidence=0.9, subject="sister's name"))
    s.add_fact(Fact(text="the user likes coffee in the morning", confidence=0.8, subject="drink"))
    hits = s.recall("tell me about my sister", k=3)
    assert hits and "Anya" in hits[0].text          # nearest is the sister fact
    assert hits[0].subject == "sister's name"


def test_recall_empty_store_returns_nothing():
    assert _store().recall("anything", k=3) == []


def test_recall_respects_k_read_budget():
    s = _store()
    for i in range(5):
        s.add_fact(Fact(text=f"the user has hobby number {i}", confidence=0.9, subject=f"hobby-{i}"))
    assert len(s.recall("hobbies", k=3)) == 3       # budget cap honored


# -- dedupe + conflict ------------------------------------------------------


def _count(s) -> int:
    return s._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]


def test_exact_text_dedupe_when_no_subject():
    s = _store()
    s.add_fact(Fact(text="the user is learning guitar", confidence=0.8))
    s.add_fact(Fact(text="the user is learning guitar", confidence=0.8))  # identical
    assert _count(s) == 1


def test_conflict_last_write_wins_on_subject():
    s = _store()
    s.add_fact(Fact(text="the user's sister is named Anya", confidence=0.9, subject="sister's name"))
    s.add_fact(Fact(text="the user's sister is named Anaya", confidence=0.95, subject="sister's name"))
    assert _count(s) == 1                            # replaced, not duplicated
    hits = s.recall("my sister", k=3)
    assert "Anaya" in hits[0].text                   # the newer value wins


# -- turns ------------------------------------------------------------------


def test_recent_turns_in_chronological_order():
    s = _store()
    s.append_turn(Message("user", "one"))
    s.append_turn(Message("assistant", "two"))
    s.append_turn(Message("user", "three"))
    recent = s.recent(limit=2)
    assert [m.content for m in recent] == ["two", "three"]  # last 2, oldest-first


# -- memory log -------------------------------------------------------------


def test_memory_log_records_writes(tmp_path):
    log = tmp_path / "memory-log.txt"
    s = _store(log=log)
    s.add_fact(Fact(text="the user's sister is named Anya", confidence=0.9, subject="sister's name"))
    s.add_fact(Fact(text="the user's sister is named Anaya", confidence=0.95, subject="sister's name"))
    text = log.read_text(encoding="utf-8")
    assert "STORED" in text and "UPDATED" in text
    assert "Anya" in text and "Anaya" in text


# -- persistence (the real-proof at unit level) -----------------------------


def test_facts_persist_across_reopen(tmp_path):
    db = str(tmp_path / "mem.db")
    s1 = SqliteMemoryStore(db, FakeEmbedder())
    s1.add_fact(Fact(text="the user's sister is named Anya", confidence=0.9, subject="sister's name"))
    s1.close()

    s2 = SqliteMemoryStore(db, FakeEmbedder())          # fresh connection, like an app restart
    hits = s2.recall("tell me about my sister", k=3)
    assert hits and "Anya" in hits[0].text


# -- extraction rejection ---------------------------------------------------


def test_parse_valid_facts():
    raw = '[{"subject":"sister","text":"the user has a sister named Anya","confidence":0.9}]'
    facts = parse_extracted_facts(raw)
    assert len(facts) == 1 and facts[0].subject == "sister" and facts[0].confidence == 0.9


def test_parse_malformed_json_returns_empty():
    assert parse_extracted_facts("not json at all") == []
    assert parse_extracted_facts("") == []
    assert parse_extracted_facts('{"not": "a list"}') == []


def test_parse_gates_low_confidence():
    raw = '[{"text":"maybe true","confidence":0.3}]'
    assert parse_extracted_facts(raw, min_confidence=0.6) == []


def test_parse_drops_items_missing_text_or_bad_confidence():
    raw = '[{"confidence":0.9},{"text":"","confidence":0.9},{"text":"ok","confidence":"high"}]'
    assert parse_extracted_facts(raw) == []


def test_parse_tolerates_code_fence():
    raw = '```json\n[{"text":"the user codes in python","confidence":0.8}]\n```'
    facts = parse_extracted_facts(raw)
    assert len(facts) == 1 and "python" in facts[0].text


# -- protection + history gating + seeding ----------------------------------


def test_conversational_extraction_cannot_overwrite_a_core_fact():
    s = _store()
    s.add_fact(Fact(text="the user's name is Mithilesh", confidence=1.0,
                    subject="user's name", origin="core"))
    # an offhand conversational fact on the same subject must NOT win
    s.add_fact(Fact(text="the user's name is Bob", confidence=0.9, subject="user's name"))
    facts = s.all_facts()
    assert len(facts) == 1
    assert "Mithilesh" in facts[0].text and facts[0].origin == "core"


def test_seeding_can_update_a_protected_fact():
    s = _store()
    s.add_fact(Fact(text="Isha is at build v1", confidence=1.0, subject="self: version", origin="self"))
    s.add_fact(Fact(text="Isha is at build v2", confidence=1.0, subject="self: version", origin="self"))
    facts = s.all_facts()
    assert len(facts) == 1 and "v2" in facts[0].text  # seed origin updates itself


def test_self_history_hidden_unless_explicitly_requested():
    s = _store()
    s.add_fact(Fact(text="Isha used to sound robotic", confidence=1.0,
                    subject="self-history: v0", origin="self_history"))
    assert s.recall("tell me about your old voice", k=3) == []          # hidden by default
    hits = s.recall("tell me about your old voice", k=3, include_history=True)
    assert hits and "robotic" in hits[0].text                            # shown when asked


def test_seed_plants_protected_facts_and_is_idempotent():
    from isha.memory.seed import seed, seed_if_needed
    s = _store()
    assert seed(s) > 0
    assert any(f.origin == "core" and "Isha" in f.text for f in s.all_facts())
    assert seed_if_needed(s) == 0  # core facts already present -> no-op
