"""SqliteMemoryStore — the v1 MemoryStore impl.

One SQLite file holds everything (portable, no server, very explainable):
  * turns  — raw conversation, for recent-history context
  * facts  — durable things learned about the user (subject, text, confidence)
  * vec_facts — sqlite-vec KNN index over the fact embeddings, for semantic recall

Trust/debug: every write is appended to a human-readable memory-log so you can SEE
exactly what Isha stored, updated, or skipped, and why.

Conflict policy (eng review): a fact WITH a subject is upserted last-write-wins on
that subject; a fact WITHOUT a subject is deduped by exact text. Recall is a
semantic top-K — the caller passes its read budget as k.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import sqlite_vec

from isha.core.interfaces import Embedder, Fact, Message


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SqliteMemoryStore:
    def __init__(self, db_path: str | Path, embedder: Embedder, *,
                 log_path: str | Path | None = None) -> None:
        self._embedder = embedder
        self._log_path = Path(log_path) if log_path else None
        self._conn = sqlite3.connect(str(db_path))
        try:
            self._conn.enable_load_extension(True)
        except AttributeError as e:  # pragma: no cover - platform guard
            raise RuntimeError(
                "This Python's sqlite3 can't load extensions, so sqlite-vec won't load. "
                "Install pysqlite3-binary or use a Python built with loadable extensions."
            ) from e
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._dim: int | None = None
        self._init_schema()

    # -- schema ------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns(
                id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT);
            CREATE TABLE IF NOT EXISTS facts(
                id INTEGER PRIMARY KEY, subject TEXT, text TEXT NOT NULL,
                confidence REAL, source_turn_id INTEGER, ts TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            """
        )
        self._conn.commit()
        # On reopen, recover the embedding dim so the vec table is recreated to match.
        row = self._conn.execute("SELECT value FROM meta WHERE key='dim'").fetchone()
        if row is not None:
            self._dim = int(row[0])
            self._ensure_vec_table()

    def _ensure_vec_table(self) -> None:
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_facts "
            f"USING vec0(fact_id INTEGER PRIMARY KEY, embedding float[{self._dim}])"
        )
        self._conn.commit()

    def _set_dim(self, dim: int) -> None:
        if self._dim is None:
            self._dim = dim
            self._conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('dim', ?)", (str(dim),))
            self._ensure_vec_table()
            self._conn.commit()

    # -- facts -------------------------------------------------------------

    def add_fact(self, fact: Fact) -> None:
        emb = self._embedder.embed([fact.text])[0]
        self._set_dim(len(emb))
        blob = sqlite_vec.serialize_float32(emb)
        cur = self._conn.cursor()

        if fact.subject:
            existing = cur.execute("SELECT id FROM facts WHERE subject = ?", (fact.subject,)).fetchone()
            if existing is not None:  # last-write-wins on the subject
                fid = existing[0]
                cur.execute(
                    "UPDATE facts SET text=?, confidence=?, source_turn_id=?, ts=? WHERE id=?",
                    (fact.text, fact.confidence, fact.source_turn_id, _now(), fid),
                )
                cur.execute("DELETE FROM vec_facts WHERE fact_id = ?", (fid,))
                cur.execute("INSERT INTO vec_facts(fact_id, embedding) VALUES(?, ?)", (fid, blob))
                self._conn.commit()
                self._log("UPDATED", fact)
                return
        else:
            dup = cur.execute(
                "SELECT id FROM facts WHERE subject IS NULL AND text = ?", (fact.text,)
            ).fetchone()
            if dup is not None:  # exact-text dedupe
                self._log("DEDUP", fact)
                return

        cur.execute(
            "INSERT INTO facts(subject, text, confidence, source_turn_id, ts) VALUES(?, ?, ?, ?, ?)",
            (fact.subject, fact.text, fact.confidence, fact.source_turn_id, _now()),
        )
        fid = cur.lastrowid
        cur.execute("INSERT INTO vec_facts(fact_id, embedding) VALUES(?, ?)", (fid, blob))
        self._conn.commit()
        self._log("STORED", fact)

    def recall(self, query: str, *, k: int = 3) -> list[Fact]:
        if self._dim is None or not query.strip():
            return []
        qblob = sqlite_vec.serialize_float32(self._embedder.embed([query])[0])
        ids = [
            row[0]
            for row in self._conn.execute(
                "SELECT fact_id FROM vec_facts WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (qblob, k),
            ).fetchall()
        ]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        by_id = {
            r[0]: Fact(text=r[2], confidence=r[3], source_turn_id=r[4], subject=r[1])
            for r in self._conn.execute(
                f"SELECT id, subject, text, confidence, source_turn_id FROM facts WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        }
        return [by_id[i] for i in ids if i in by_id]  # preserve nearest-first order

    # -- turns -------------------------------------------------------------

    def append_turn(self, message: Message) -> int:
        cur = self._conn.execute(
            "INSERT INTO turns(role, content, ts) VALUES(?, ?, ?)",
            (message.role, message.content, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent(self, *, limit: int = 20) -> list[Message]:
        rows = self._conn.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Message(role=r[0], content=r[1]) for r in reversed(rows)]

    # -- misc --------------------------------------------------------------

    def _log(self, action: str, fact: Fact) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (f"[{_now()}] {action:7} subject={fact.subject!r} "
                f"conf={fact.confidence} text={fact.text!r}\n")
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def close(self) -> None:
        self._conn.close()
