"""Tests for the polarity-flip monitor (Feature C)."""

import tempfile
from pathlib import Path

from paperpulse.models import Paper
from paperpulse.contradiction import ContradictionPair
from paperpulse.polarity import PolarityMonitor


def _pair(pol_a: int = 1, pol_b: int = -1) -> ContradictionPair:
    return ContradictionPair(
        a=Paper(id="a1", title="Paper A", abstract="improves returns"),
        b=Paper(id="b1", title="Paper B", abstract="fails to replicate"),
        similarity=0.75,
        note="test",
        polarity_a=pol_a,
        polarity_b=pol_b,
    )


def test_record_no_flip_on_first():
    with tempfile.TemporaryDirectory() as tmp:
        mon = PolarityMonitor(Path(tmp) / "pol.db")
        try:
            flips = mon.record_and_detect_flips([_pair()])
            assert flips == []
            assert mon.stats()["tracked_pairs"] == 1
        finally:
            mon.close()


def test_detect_flip():
    with tempfile.TemporaryDirectory() as tmp:
        mon = PolarityMonitor(Path(tmp) / "pol.db")
        try:
            mon.record_and_detect_flips([_pair(pol_a=1, pol_b=-1)])
            flips = mon.record_and_detect_flips([_pair(pol_a=-1, pol_b=1)])
            assert len(flips) == 1
            assert flips[0].old_polarity_a == 1
            assert flips[0].new_polarity_a == -1
            assert mon.stats()["total_flips"] == 1
        finally:
            mon.close()


def test_no_flip_same_polarity():
    with tempfile.TemporaryDirectory() as tmp:
        mon = PolarityMonitor(Path(tmp) / "pol.db")
        try:
            mon.record_and_detect_flips([_pair(pol_a=1, pol_b=-1)])
            flips = mon.record_and_detect_flips([_pair(pol_a=1, pol_b=-1)])
            assert flips == []
            assert mon.stats()["total_flips"] == 0
        finally:
            mon.close()


def test_consensus_volatility():
    with tempfile.TemporaryDirectory() as tmp:
        mon = PolarityMonitor(Path(tmp) / "pol.db")
        try:
            mon.record_and_detect_flips([_pair(pol_a=1, pol_b=-1)])
            mon.record_and_detect_flips([_pair(pol_a=-1, pol_b=1)])
            mon.record_and_detect_flips([_pair(pol_a=1, pol_b=-1)])
            vol = mon.consensus_volatility()
            assert len(vol) == 1
            key = list(vol.keys())[0]
            assert vol[key] > 0
        finally:
            mon.close()


def test_history():
    with tempfile.TemporaryDirectory() as tmp:
        mon = PolarityMonitor(Path(tmp) / "pol.db")
        try:
            mon.record_and_detect_flips([_pair()])
            mon.record_and_detect_flips([_pair(pol_a=-1, pol_b=1)])
            key = "a1|b1"
            hist = mon.history(key)
            assert len(hist) == 2
        finally:
            mon.close()
