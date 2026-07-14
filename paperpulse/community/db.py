"""SQLite storage for the community trust layer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
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
CREATE TABLE IF NOT EXISTS annotations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id   TEXT NOT NULL,
    user       TEXT NOT NULL DEFAULT 'anon',
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_paper ON annotations(paper_id);
"""


@dataclass
class Annotation:
    paper_id: str
    user: str
    body: str
    created_at: str


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

    def consensus_trust(self, paper_id: str) -> dict | None:
        """Pooled trust for a paper across all users."""
        row = self._conn.execute(
            "SELECT AVG(score) AS avg_score, COUNT(*) AS n "
            "FROM trust_reports WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        if not row or row["n"] == 0:
            return None
        return {"paper_id": paper_id, "avg_score": row["avg_score"], "reports": row["n"]}

    # --- annotations --------------------------------------------------------
    def add_annotation(self, paper_id: str, body: str, *, user: str = "anon") -> None:
        self._conn.execute(
            "INSERT INTO annotations (paper_id, user, body, created_at) "
            "VALUES (?, ?, ?, ?)",
            (paper_id, user, body, _now()),
        )
        self._conn.commit()

    def annotations(self, paper_id: str) -> list[Annotation]:
        rows = self._conn.execute(
            "SELECT paper_id, user, body, created_at FROM annotations "
            "WHERE paper_id = ? ORDER BY created_at",
            (paper_id,),
        ).fetchall()
        return [Annotation(**dict(r)) for r in rows]

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
