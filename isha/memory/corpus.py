"""Learned knowledge — documents he hands her, retrievable in conversation.

Roadmap step 8. Third lifecycle on the same database file, alongside facts (slots) and
episodes (events): a corpus is a BODY OF TEXT she was given. Named, append-only,
deleted whole. "Learning a skill" is ingesting the sources; "keeping it permanently" is
the corpus persisting; "forgetting it" is dropping the collection.

The honest ceiling, stated up front: this makes her able to answer *from his documents*.
It does not make her an expert. Fine-tuning to expert level was ruled infeasible on 4GB
VRAM in DESIGN.md and reframed as retrieval, and retrieval over a 3B with a 4096-token
context is a lookup, not mastery. She quotes the source or says she has nothing.

No new dependencies: the same sqlite-vec + fastembed the fact store already uses.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec

READABLE = (".txt", ".md", ".markdown", ".rst")


@dataclass(frozen=True)
class Passage:
    corpus: str
    source: str          # filename it came from, so she can say where she read it
    text: str
    distance: float      # cosine distance; lower is closer


def chunk_text(text: str, *, chunk_chars: int = 800) -> list[str]:
    """Split on blank lines, then pack paragraphs up to the budget.

    Paragraph boundaries rather than a fixed window: a chunk cut mid-sentence embeds
    badly and reads worse when she says it out loud. A single paragraph longer than the
    budget is left whole — splitting it would do the damage the packing avoids.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > chunk_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


class CorpusStore:
    def __init__(self, db_path: str | Path, embedder) -> None:
        self._embedder = embedder
        self._conn = sqlite3.connect(str(db_path))
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS corpus_chunks(
                id INTEGER PRIMARY KEY,
                corpus TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS corpus_vectors(
                chunk_id INTEGER PRIMARY KEY, embedding BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS corpus_by_name ON corpus_chunks(corpus);
            """
        )
        self._conn.commit()

    # -- writing -----------------------------------------------------------

    def ingest(self, corpus: str, path: str | Path, *, chunk_chars: int = 800) -> int:
        """Read a file (or every readable file in a folder) into `corpus`.

        Returns the number of chunks stored. Re-ingesting the same source replaces it,
        so fixing a typo in a document and running again does not double every answer.
        """
        path = Path(path)
        files = ([p for p in sorted(path.rglob("*")) if p.suffix.lower() in READABLE]
                 if path.is_dir() else [path])
        if not files:
            return 0
        stored = 0
        for file in files:
            text = file.read_text(encoding="utf-8", errors="replace")
            chunks = chunk_text(text, chunk_chars=chunk_chars)
            if not chunks:
                continue
            self._drop_source(corpus, file.name)
            vectors = self._embedder.embed(chunks)
            for chunk, vector in zip(chunks, vectors):
                cur = self._conn.execute(
                    "INSERT INTO corpus_chunks(corpus, source, text) VALUES(?, ?, ?)",
                    (corpus, file.name, chunk))
                self._conn.execute(
                    "INSERT INTO corpus_vectors(chunk_id, embedding) VALUES(?, ?)",
                    (int(cur.lastrowid), sqlite_vec.serialize_float32(vector)))
                stored += 1
        self._conn.commit()
        return stored

    def _drop_source(self, corpus: str, source: str) -> None:
        ids = [r[0] for r in self._conn.execute(
            "SELECT id FROM corpus_chunks WHERE corpus=? AND source=?", (corpus, source))]
        self._delete(ids)

    def _delete(self, ids: list[int]) -> None:
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(f"DELETE FROM corpus_vectors WHERE chunk_id IN ({placeholders})", ids)
        self._conn.execute(f"DELETE FROM corpus_chunks WHERE id IN ({placeholders})", ids)

    def forget(self, corpus: str) -> int:
        ids = [r[0] for r in self._conn.execute(
            "SELECT id FROM corpus_chunks WHERE corpus=?", (corpus,))]
        self._delete(ids)
        self._conn.commit()
        return len(ids)

    # -- reading -----------------------------------------------------------

    def corpora(self) -> list[tuple[str, int, int]]:
        """(name, chunks, sources) for everything she has learned."""
        return [(r[0], r[1], r[2]) for r in self._conn.execute(
            "SELECT corpus, COUNT(*), COUNT(DISTINCT source) FROM corpus_chunks "
            "GROUP BY corpus ORDER BY corpus")]

    def search(self, query: str, *, k: int = 2, max_distance: float = 1.0) -> list[Passage]:
        """Closest passages, nearest first, dropping anything past `max_distance`.

        The distance gate is what keeps this out of ordinary conversation: a chat about
        his day should not drag in a paragraph about a corpus topic just because it was
        the least-bad match. Nothing close enough means nothing injected.
        """
        if not query.strip():
            return []
        if not self._conn.execute("SELECT 1 FROM corpus_chunks LIMIT 1").fetchone():
            return []
        blob = sqlite_vec.serialize_float32(self._embedder.embed([query])[0])
        rows = self._conn.execute(
            "SELECT c.corpus, c.source, c.text, vec_distance_cosine(v.embedding, ?) AS d "
            "FROM corpus_vectors v JOIN corpus_chunks c ON c.id = v.chunk_id "
            "ORDER BY d LIMIT ?", (blob, k)).fetchall()
        return [Passage(corpus=r[0], source=r[1], text=r[2], distance=r[3])
                for r in rows if r[3] <= max_distance]

    def close(self) -> None:
        self._conn.close()
