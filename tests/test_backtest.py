"""The optopsy backtest bridge: synthetic data, and graceful degradation
when the (optional, AGPL, Python 3.12+) optopsy dependency isn't present."""

import pytest

from paperpulse import backtest
from paperpulse.alpha import AlphaCard


def test_synthetic_chain_shape():
    rows = backtest._synthetic_chain(cycles=1, dte=10)
    assert len(rows) > 0
    assert all(len(r) == 8 for r in rows)  # matches _COLUMNS
    types = {r[1] for r in rows}
    assert types == {"call", "put"}
    # Deltas stay within valid, non-degenerate bounds.
    deltas = [r[7] for r in rows]
    assert all(-1 < d < 1 for d in deltas)
    calls = [r[7] for r in rows if r[1] == "call"]
    puts = [r[7] for r in rows if r[1] == "put"]
    assert all(d > 0 for d in calls)
    assert all(d < 0 for d in puts)


def test_synthetic_chain_covers_full_dte_range():
    """A backtest needs the same contract quoted from entry through exit --
    not just an isolated snapshot."""
    rows = backtest._synthetic_chain(cycles=1, dte=20)
    from datetime import datetime

    quote_dates = {r[3] for r in rows}
    expirations = {r[2] for r in rows}
    assert len(expirations) == 1  # one cycle -> one expiration
    (expiration,) = expirations
    assert expiration in quote_dates  # exit-day (DTE 0) quote exists
    parsed = [datetime.strptime(d, "%m/%d/%Y") for d in quote_dates]
    span = (max(parsed) - min(parsed)).days
    assert span == 20  # a full dte-day timeline, not a handful of snapshots


def test_synthetic_chain_has_intrinsic_value():
    """Deep ITM options must cost close to intrinsic value, or a breached
    short strike never actually costs anything to close -- see the historical
    bug where every synthetic iron condor trade won."""
    rows = backtest._synthetic_chain(cycles=1, dte=30, seed=1)
    # Deep ITM calls (strike far below spot) should be priced near their
    # intrinsic value, not near the small at-the-money time-value premium.
    deep_itm_calls = [r for r in rows if r[1] == "call" and r[7] > 0.95]
    atm_calls = [r for r in rows if r[1] == "call" and abs(r[7] - 0.5) < 0.05]
    assert deep_itm_calls and atm_calls
    assert max(r[5] for r in deep_itm_calls) > 3 * max(r[6] for r in atm_calls)


@pytest.mark.skipif(backtest.OPTOPSY_AVAILABLE, reason="only tests the missing-dependency path")
def test_run_demo_without_optopsy_raises_friendly_error():
    with pytest.raises(RuntimeError, match="paperpulse\\[backtest\\]"):
        backtest.run_demo()


@pytest.mark.skipif(not backtest.OPTOPSY_AVAILABLE, reason="needs optopsy + Python 3.12+")
def test_run_demo_produces_real_trades_with_wins_and_losses():
    """The whole point of the demo is to show real backtest mechanics --
    including that short-premium strategies can lose, not just win."""
    demo = backtest.run_demo()
    assert demo.strategy == "iron_condor"
    assert len(demo.aggregated) > 0
    win_rates = demo.aggregated["win_rate"]
    assert win_rates.min() < 1.0  # at least one bucket has a loss
    assert win_rates.max() > 0.0  # at least one bucket has a win


@pytest.mark.skipif(not backtest.OPTOPSY_AVAILABLE, reason="needs optopsy + Python 3.12+")
def test_run_demo_surfaces_card_context_in_notes():
    card = AlphaCard(claim="X predicts Y", data_sources=["CRSP"], period="1990-2020")
    demo = backtest.run_demo(card)
    joined = " ".join(demo.notes)
    assert "X predicts Y" in joined
    assert "CRSP" in joined
    assert "1990-2020" in joined
