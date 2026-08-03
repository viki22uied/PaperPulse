"""Immutable prediction ledger: every trust flag recorded at assessment time.

Each row is a (paper, signal, status, score, timestamp) tuple that never
changes after insertion.  Reconcilers later attach outcomes to these rows
and the calibration module computes hit-rates per badge tier.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS flag_ledger (
    paper_id   TEXT    NOT NULL,
    doi        TEXT,
    signal     TEXT    NOT NULL,
    status     TEXT    NOT NULL,
    confidence REAL    NOT NULL DEFAULT 1.0,
    weight     REAL    NOT NULL DEFAULT 1.0,
    hygiene    INTEGER NOT NULL DEFAULT 0,
    note       TEXT,
    evidence   TEXT,
    score      REAL    NOT NULL,
    badge      TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    PRIMARY KEY (paper_id, signal, created_at)
);

CREATE TABLE IF NOT EXISTS outcomes (
    paper_id    TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    source      TEXT NOT NULL,
    detail      TEXT,
    resolved_at TEXT NOT NULL,
    PRIMARY KEY (paper_id, outcome, source)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_paper ON outcomes(paper_id);
CREATE INDEX IF NOT EXISTS idx_ledger_badge ON flag_ledger(badge);
CREATE INDEX IF NOT EXISTS idx_ledger_paper ON flag_ledger(paper_id);
"""

_now = lambda: datetime.now(timezone.utc).isoformat()


class ValidationLedger:
    def __init__(self, path: str | Path = "paperpulse_validation.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record_flags(
        self,
        paper_id: str,
        *,
        doi: str = "",
        signals: list[dict],
        score: float,
        badge: str,
    ) -> int:
        ts = _now()
        rows = 0
        for s in signals:
            try:
                self._conn.execute(
                    "INSERT OR IGNORE INTO flag_ledger "
                    "(paper_id, doi, signal, status, confidence, weight, "
                    " hygiene, note, evidence, score, badge, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        paper_id,
                        doi or None,
                        s["name"],
                        s["status"],
                        s.get("confidence", 1.0),
                        s.get("weight", 1.0),
                        int(s.get("hygiene", False)),
                        s.get("note", ""),
                        s.get("evidence", ""),
                        score,
                        badge,
                        ts,
                    ),
                )
                rows += 1
            except sqlite3.IntegrityError:
                pass
        self._conn.commit()
        return rows

    def record_outcome(
        self,
        paper_id: str,
        *,
        outcome: str,
        source: str,
        detail: str = "",
    ) -> bool:
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO outcomes "
            "(paper_id, outcome, source, detail, resolved_at) "
            "VALUES (?,?,?,?,?)",
            (paper_id, outcome, source, detail, _now()),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def papers_with_badge(self, badge: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT paper_id FROM flag_ledger WHERE badge = ?",
            (badge,),
        ).fetchall()
        return [r["paper_id"] for r in rows]

    def all_paper_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT paper_id FROM flag_ledger"
        ).fetchall()
        return [r["paper_id"] for r in rows]

    def dois(self) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT DISTINCT paper_id, doi FROM flag_ledger WHERE doi IS NOT NULL"
        ).fetchall()
        return {r["paper_id"]: r["doi"] for r in rows}

    def outcomes_for(self, paper_ids: list[str]) -> dict[str, list[dict]]:
        if not paper_ids:
            return {}
        ph = ",".join("?" * len(paper_ids))
        rows = self._conn.execute(
            f"SELECT * FROM outcomes WHERE paper_id IN ({ph})", paper_ids
        ).fetchall()
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["paper_id"], []).append(dict(r))
        return out

    def badge_for(self, paper_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT badge FROM flag_ledger WHERE paper_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (paper_id,),
        ).fetchone()
        return row["badge"] if row else None

    def flags_for(self, paper_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT signal, status, confidence, weight, hygiene, note, evidence "
            "FROM flag_ledger WHERE paper_id = ? AND status != 'ok' AND hygiene = 0",
            (paper_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        papers = self._conn.execute(
            "SELECT COUNT(DISTINCT paper_id) as n FROM flag_ledger"
        ).fetchone()
        outcomes = self._conn.execute(
            "SELECT COUNT(DISTINCT paper_id) as n FROM outcomes"
        ).fetchone()
        by_badge = self._conn.execute(
            "SELECT badge, COUNT(DISTINCT paper_id) as n "
            "FROM flag_ledger GROUP BY badge"
        ).fetchall()
        by_outcome = self._conn.execute(
            "SELECT outcome, COUNT(*) as n FROM outcomes GROUP BY outcome"
        ).fetchall()
        return {
            "total_papers": papers["n"],
            "papers_with_outcomes": outcomes["n"],
            "by_badge": {r["badge"]: r["n"] for r in by_badge},
            "by_outcome": {r["outcome"]: r["n"] for r in by_outcome},
        }
