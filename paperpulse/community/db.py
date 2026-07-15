"""SQLite storage for the community trust layer."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_reports (
    paper_id   TEXT NOT NULL,
    user       TEXT NOT NULL DEFAULT 'anon',
    score      REAL NOT NULL,
    badge      TEXT NOT NULL,
    flags      TEXT NOT NULL,     -- JSON list of flagged signal names
    venue      TEXT,
    authors    TEXT,              -- JSON list
    created_at TEXT NOT NULL,
    PRIMARY KEY (paper_id, user)
);
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id   TEXT NOT NULL,
    user       TEXT NOT NULL DEFAULT 'anon',
    note       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommunityDB:
    def __init__(self, path: str | Path = "paperpulse_community.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- trust reports ------------------------------------------------------
    def record_trust(
        self,
        paper_id: str,
        *,
        score: float,
        badge: str,
        flags: list[str],
        venue: str | None = None,
        authors: list[str] | None = None,
        user: str = "anon",
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO trust_reports "
            "(paper_id, user, score, badge, flags, venue, authors, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                paper_id,
                user,
                score,
                badge,
                json.dumps(flags),
                venue,
                json.dumps(authors or []),
                _now(),
            ),
        )
        self._conn.commit()

    # --- leaderboard --------------------------------------------------------
    def flag_leaderboard(self, limit: int = 20) -> list[dict]:
        """Authors ranked by how often their papers were flagged. Deliberately
        conservative: only counts reports that actually carried a flag."""
        rows = self._conn.execute(
            "SELECT authors, flags FROM trust_reports"
        ).fetchall()
        counts: dict[str, dict] = {}
        for row in rows:
            flags = json.loads(row["flags"])
            if not flags:
                continue
            for author in json.loads(row["authors"] or "[]"):
                entry = counts.setdefault(author, {"author": author, "flagged": 0, "flags": 0})
                entry["flagged"] += 1
                entry["flags"] += len(flags)
        board = sorted(counts.values(), key=lambda e: e["flags"], reverse=True)
        return board[:limit]

    # --- annotations ---------------------------------------------------------
    def add_note(self, paper_id: str, note: str, *, user: str = "anon") -> None:
        """Save a free-text note against a paper, so the digest can double as
        a personal reading library, not just a one-shot feed."""
        self._conn.execute(
            "INSERT INTO notes (paper_id, user, note, created_at) VALUES (?, ?, ?, ?)",
            (paper_id, user, note, _now()),
        )
        self._conn.commit()

    def get_notes(self, paper_id: str, *, user: str | None = None) -> list[dict]:
        query = "SELECT * FROM notes WHERE paper_id = ?"
        params: list = [paper_id]
        if user is not None:
            query += " AND user = ?"
            params.append(user)
        query += " ORDER BY created_at"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
