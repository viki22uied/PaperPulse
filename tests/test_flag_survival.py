"""Tests for the community flag-survival leaderboard (Feature D)."""

import tempfile
from pathlib import Path

from paperpulse.community.db import CommunityDB


def test_record_flag_outcome():
    with tempfile.TemporaryDirectory() as tmp:
        db = CommunityDB(Path(tmp) / "comm.db")
        try:
            db.record_flag_outcome("leakage", confirmed=True)
            db.record_flag_outcome("leakage", confirmed=True)
            db.record_flag_outcome("leakage", confirmed=False)
            report = db.flag_survival_report()
            assert len(report) == 1
            assert report[0]["signal"] == "leakage"
            assert report[0]["total"] == 3
            assert report[0]["confirmed"] == 2
            assert report[0]["false_positives"] == 1
            assert abs(report[0]["precision"] - 0.667) < 0.01
        finally:
            db.close()


def test_multiple_signals():
    with tempfile.TemporaryDirectory() as tmp:
        db = CommunityDB(Path(tmp) / "comm.db")
        try:
            db.record_flag_outcome("leakage", confirmed=True)
            db.record_flag_outcome("overclaim", confirmed=False)
            db.record_flag_outcome("overclaim", confirmed=True)
            report = db.flag_survival_report()
            assert len(report) == 2
            by_name = {r["signal"]: r for r in report}
            assert by_name["leakage"]["precision"] == 1.0
            assert by_name["overclaim"]["precision"] == 0.5
        finally:
            db.close()


def test_empty_report():
    with tempfile.TemporaryDirectory() as tmp:
        db = CommunityDB(Path(tmp) / "comm.db")
        try:
            assert db.flag_survival_report() == []
        finally:
            db.close()
