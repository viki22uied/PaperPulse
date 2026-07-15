"""Shared "known/already-tried topic" log.

One SQLite table backs two ideas that turn out to be the same thing: a
maintained list of well-known factor families (so semantic similarity alone
doesn't miss "betting against beta" == "low-volatility anomaly"), and a
personal log of what you've already tried and how it went. ``source``
distinguishes the two ("literature" vs "manual"); everything else -- matching,
storage, CLI -- is shared so they never have to be reconciled later.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    name       TEXT PRIMARY KEY,
    aliases    TEXT NOT NULL DEFAULT '',   -- comma-separated
    source     TEXT NOT NULL DEFAULT 'manual',   -- manual | literature
    result     TEXT NOT NULL DEFAULT 'untested',  -- dead | weak | promising | untested
    region     TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

RESULTS = {"dead", "weak", "promising", "untested"}


@dataclass
class TopicEntry:
    name: str
    aliases: list[str] = field(default_factory=list)
    source: str = "manual"
    result: str = "untested"
    region: str = ""
    notes: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


class TopicLog:
    def __init__(self, path: str | Path = "paperpulse_topics.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        name: str,
        *,
        aliases: list[str] | None = None,
        source: str = "manual",
        result: str = "untested",
        region: str = "",
        notes: str = "",
    ) -> None:
        if result not in RESULTS:
            raise ValueError(f"result must be one of {sorted(RESULTS)}")
        self._conn.execute(
            "INSERT OR REPLACE INTO topics "
            "(name, aliases, source, result, region, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, ",".join(aliases or []), source, result, region, notes, _now()),
        )
        self._conn.commit()

    def all(self) -> list[TopicEntry]:
        rows = self._conn.execute("SELECT * FROM topics").fetchall()
        return [
            TopicEntry(
                name=r["name"],
                aliases=[a for a in r["aliases"].split(",") if a],
                source=r["source"],
                result=r["result"],
                region=r["region"],
                notes=r["notes"],
            )
            for r in rows
        ]


def match_text(text: str, entries: list[TopicEntry], *, threshold: float = 0.9) -> TopicEntry | None:
    """Best matching topic for ``text`` (a paper's title + abstract), or None.

    Deterministic: an exact substring hit on the name or any alias always
    matches. Otherwise falls back to a close (near-exact wording) match via
    stdlib ``difflib`` so minor phrasing differences don't miss -- this is not
    meant to catch loose semantic paraphrase, just typos/pluralization."""
    haystack = _normalize(text)
    for entry in entries:
        candidates = [entry.name, *entry.aliases]
        for cand in candidates:
            cand_norm = _normalize(cand)
            if not cand_norm:
                continue
            if cand_norm in haystack:
                return entry
        words = haystack.split()
        for cand in candidates:
            cand_norm = _normalize(cand)
            if not cand_norm:
                continue
            n = len(cand_norm.split())
            for i in range(0, max(len(words) - n + 1, 0)):
                window = " ".join(words[i : i + n])
                if difflib.SequenceMatcher(None, window, cand_norm).ratio() >= threshold:
                    return entry
    return None


__all__ = ["TopicEntry", "TopicLog", "match_text", "RESULTS"]
