"""Tests for the prospective flag-validation ledger (Feature A)."""

import tempfile
from pathlib import Path

from paperpulse.validation.ledger import ValidationLedger
from paperpulse.validation.calibration import calibration_report


def test_ledger_record_and_retrieve():
    with tempfile.TemporaryDirectory() as tmp:
        db = ValidationLedger(Path(tmp) / "test.db")
        try:
            n = db.record_flags(
                "2401.00001",
                doi="10.1234/test",
                signals=[
                    {"name": "leakage", "status": "flag", "confidence": 0.75,
                     "weight": 1.5, "hygiene": False, "note": "test", "evidence": "k-fold"},
                    {"name": "peer_review", "status": "warn", "confidence": 0.6,
                     "weight": 1.0, "hygiene": True, "note": "preprint", "evidence": ""},
                ],
                score=0.65,
                badge="mixed",
            )
            assert n == 2
            assert db.badge_for("2401.00001") == "mixed"
            flags = db.flags_for("2401.00001")
            assert len(flags) == 1
            assert flags[0]["signal"] == "leakage"
        finally:
            db.close()


def test_ledger_outcomes():
    with tempfile.TemporaryDirectory() as tmp:
        db = ValidationLedger(Path(tmp) / "test.db")
        try:
            db.record_flags(
                "2401.00001",
                signals=[{"name": "overclaim", "status": "warn", "note": ""}],
                score=0.8,
                badge="clean",
            )
            ok = db.record_outcome(
                "2401.00001", outcome="retracted", source="crossref", detail="test"
            )
            assert ok
            dup = db.record_outcome(
                "2401.00001", outcome="retracted", source="crossref"
            )
            assert not dup

            outcomes = db.outcomes_for(["2401.00001"])
            assert "2401.00001" in outcomes
            assert outcomes["2401.00001"][0]["outcome"] == "retracted"
        finally:
            db.close()


def test_calibration_report():
    with tempfile.TemporaryDirectory() as tmp:
        db = ValidationLedger(Path(tmp) / "test.db")
        try:
            for i, badge in enumerate(["clean", "clean", "clean", "mixed", "caution"]):
                db.record_flags(
                    f"paper_{i}",
                    signals=[{"name": "test", "status": "ok", "note": ""}],
                    score={"clean": 0.9, "mixed": 0.6, "caution": 0.3}[badge],
                    badge=badge,
                )
            db.record_outcome("paper_4", outcome="retracted", source="test")

            result = calibration_report(db)
            assert result.total_papers == 5
            assert result.total_outcomes == 1
            caution_bucket = next(b for b in result.buckets if b.badge == "caution")
            assert caution_bucket.with_outcome == 1
            assert caution_bucket.outcome_rate == 1.0
            clean_bucket = next(b for b in result.buckets if b.badge == "clean")
            assert clean_bucket.with_outcome == 0
        finally:
            db.close()


def test_ledger_stats():
    with tempfile.TemporaryDirectory() as tmp:
        db = ValidationLedger(Path(tmp) / "test.db")
        try:
            db.record_flags(
                "p1",
                signals=[{"name": "s1", "status": "warn", "note": ""}],
                score=0.7, badge="mixed",
            )
            db.record_flags(
                "p2",
                signals=[{"name": "s1", "status": "ok", "note": ""}],
                score=0.9, badge="clean",
            )
            db.record_outcome("p1", outcome="retracted", source="test")
            s = db.stats()
            assert s["total_papers"] == 2
            assert s["papers_with_outcomes"] == 1
        finally:
            db.close()
