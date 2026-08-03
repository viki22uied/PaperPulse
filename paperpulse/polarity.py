"""Live polarity-flip monitor (Feature C).

Tracks contradiction-pair polarity over time in a SQLite table and emits
events when a pair flips agreement<->contradiction.  Builds on the existing
contradiction_map() + snapshot diff infra, adding persistent per-pair
time-series and a "consensus volatility" metric per topic.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .contradiction import ContradictionPair


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS polarity_log (
    pair_key    TEXT NOT NULL,
    paper_a_id  TEXT NOT NULL,
    paper_b_id  TEXT NOT NULL,
    paper_a_title TEXT,
    paper_b_title TEXT,
    similarity  REAL NOT NULL,
    polarity_a  INTEGER NOT NULL,
    polarity_b  INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (pair_key, recorded_at)
);

CREATE TABLE IF NOT EXISTS polarity_flips (
    pair_key       TEXT NOT NULL,
    old_polarity_a INTEGER NOT NULL,
    new_polarity_a INTEGER NOT NULL,
    flipped_at     TEXT NOT NULL,
    note           TEXT,
    PRIMARY KEY (pair_key, flipped_at)
);

CREATE INDEX IF NOT EXISTS idx_polarity_pair ON polarity_log(pair_key);
CREATE INDEX IF NOT EXISTS idx_flips_time ON polarity_flips(flipped_at);
"""

_now = lambda: datetime.now(timezone.utc).isoformat()


def _pair_key(a_id: str, b_id: str) -> str:
    return f"{min(a_id, b_id)}|{max(a_id, b_id)}"


@dataclass
class PolarityFlipEvent:
    pair_key: str
    paper_a_title: str
    paper_b_title: str
    old_polarity_a: int
    new_polarity_a: int
    flipped_at: str
    note: str = ""


class PolarityMonitor:
    def __init__(self, path: str | Path = "paperpulse_polarity.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record_and_detect_flips(
        self, pairs: list[ContradictionPair]
    ) -> list[PolarityFlipEvent]:
        ts = _now()
        flips: list[PolarityFlipEvent] = []

        for pair in pairs:
            key = _pair_key(pair.a.id, pair.b.id)

            prev = self._conn.execute(
                "SELECT polarity_a, polarity_b FROM polarity_log "
                "WHERE pair_key = ? ORDER BY recorded_at DESC LIMIT 1",
                (key,),
            ).fetchone()

            self._conn.execute(
                "INSERT OR IGNORE INTO polarity_log "
                "(pair_key, paper_a_id, paper_b_id, paper_a_title, "
                " paper_b_title, similarity, polarity_a, polarity_b, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    pair.a.id,
                    pair.b.id,
                    pair.a.title,
                    pair.b.title,
                    pair.similarity,
                    pair.polarity_a,
                    pair.polarity_b,
                    ts,
                ),
            )

            if prev and prev["polarity_a"] != pair.polarity_a:
                old_side = "positive" if prev["polarity_a"] > 0 else "negative"
                new_side = "positive" if pair.polarity_a > 0 else "negative"
                note = (
                    f"'{pair.a.title}' flipped from {old_side} to {new_side} "
                    f"relative to '{pair.b.title}'"
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO polarity_flips "
                    "(pair_key, old_polarity_a, new_polarity_a, flipped_at, note) "
                    "VALUES (?,?,?,?,?)",
                    (key, prev["polarity_a"], pair.polarity_a, ts, note),
                )
                flips.append(PolarityFlipEvent(
                    pair_key=key,
                    paper_a_title=pair.a.title,
                    paper_b_title=pair.b.title,
                    old_polarity_a=prev["polarity_a"],
                    new_polarity_a=pair.polarity_a,
                    flipped_at=ts,
                    note=note,
                ))

        self._conn.commit()
        return flips

    def history(self, pair_key: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM polarity_log WHERE pair_key = ? "
            "ORDER BY recorded_at",
            (pair_key,),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_flips(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM polarity_flips ORDER BY flipped_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def consensus_volatility(self) -> dict[str, float]:
        """Per-pair flip frequency: number of flips / number of observations."""
        pairs = self._conn.execute(
            "SELECT pair_key, COUNT(*) as n FROM polarity_log GROUP BY pair_key"
        ).fetchall()
        flips = self._conn.execute(
            "SELECT pair_key, COUNT(*) as n FROM polarity_flips GROUP BY pair_key"
        ).fetchall()
        flip_counts = {r["pair_key"]: r["n"] for r in flips}
        return {
            r["pair_key"]: round(flip_counts.get(r["pair_key"], 0) / r["n"], 3)
            for r in pairs
            if r["n"] > 1
        }

    def stats(self) -> dict:
        pairs = self._conn.execute(
            "SELECT COUNT(DISTINCT pair_key) as n FROM polarity_log"
        ).fetchone()
        observations = self._conn.execute(
            "SELECT COUNT(*) as n FROM polarity_log"
        ).fetchone()
        flips = self._conn.execute(
            "SELECT COUNT(*) as n FROM polarity_flips"
        ).fetchone()
        return {
            "tracked_pairs": pairs["n"],
            "total_observations": observations["n"],
            "total_flips": flips["n"],
        }
