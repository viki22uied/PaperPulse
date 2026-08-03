"""Tests for the finance paper overfitting screener (Feature B)."""

from paperpulse.models import Paper
from paperpulse.trust.overfitting import (
    factor_zoo_hurdle_signal,
    deflation_gap_signal,
    no_oos_validation_signal,
)


def test_factor_zoo_below_hurdle():
    paper = Paper(
        id="1", title="A new factor",
        abstract="We find a t-statistic of 2.30 for momentum returns.",
    )
    sig = factor_zoo_hurdle_signal(paper)
    assert sig.status == "warn"
    assert "factor-zoo" in sig.note.lower()


def test_factor_zoo_clears_hurdle():
    paper = Paper(
        id="2", title="Strong factor",
        abstract="The factor has a t-statistic of 4.50.",
    )
    sig = factor_zoo_hurdle_signal(paper)
    assert sig.status == "ok"


def test_factor_zoo_below_conventional():
    paper = Paper(
        id="3", title="Weak factor",
        abstract="We report a t-stat of 1.50 for cross-sectional returns.",
    )
    sig = factor_zoo_hurdle_signal(paper)
    assert sig.status == "flag"


def test_deflation_gap_no_trials():
    paper = Paper(
        id="4", title="Strategy test",
        abstract="Our strategy achieves a Sharpe ratio of 1.82.",
    )
    sig = deflation_gap_signal(paper)
    assert sig.status == "warn"
    assert "deflat" in sig.note.lower() or "trial" in sig.note.lower()


def test_deflation_gap_with_correction():
    paper = Paper(
        id="5", title="Careful strategy",
        abstract="After Bonferroni correction, the Sharpe ratio of 1.82 remains significant.",
    )
    sig = deflation_gap_signal(paper)
    assert sig.status == "ok"


def test_no_oos_missing():
    paper = Paper(
        id="6", title="In-sample only",
        abstract="We find a Sharpe ratio of 2.10 on historical data from 2000 to 2020.",
    )
    sig = no_oos_validation_signal(paper)
    assert sig.status == "warn"


def test_no_oos_present():
    paper = Paper(
        id="7", title="Validated strategy",
        abstract="The Sharpe ratio of 1.50 persists in our out-of-sample validation period.",
    )
    sig = no_oos_validation_signal(paper)
    assert sig.status == "ok"


def test_no_finance_claim():
    paper = Paper(
        id="8", title="Attention is all you need",
        abstract="We propose a new architecture for neural machine translation.",
    )
    assert factor_zoo_hurdle_signal(paper).status == "ok"
    assert deflation_gap_signal(paper).status == "ok"
    assert no_oos_validation_signal(paper).status == "ok"
