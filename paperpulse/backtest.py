"""A bridge from an alpha card to a real, runnable options backtest.

PaperPulse can tell you a paper claims something about options markets; it
cannot tell you whether that claim survives real money. This module doesn't
try to close that gap -- it teaches the *mechanics* instead: how strikes get
selected by delta, how a multi-leg position like an iron condor is built, and
what a backtest engine actually reports (P&L distribution, Sharpe, drawdown).

It runs on `optopsy <https://github.com/goldspanlabs/optopsy>`_, a real
options-backtesting library -- not a toy reimplementation. Two honest limits,
stated up front rather than glossed over:

* **Optopsy is AGPL-3.0-licensed** and only installed if you opt into the
  ``backtest`` extra (``pip install paperpulse[backtest]``). PaperPulse itself
  stays MIT; nothing here bundles or redistributes optopsy's code.
* **The data is synthetic.** Optopsy needs a real historical options chain and
  doesn't ship one -- real chains are commercial data (its own docs point at
  EODHD). Generating one here would either require you to buy data before you
  can even try the feature, or ship data whose license terms aren't ours to
  redistribute. So this module fabricates a small, clearly-synthetic SPX-shaped
  chain instead: enough rows to exercise the whole pipeline (data load, delta
  targeting, multi-leg construction, risk metrics) without claiming to test
  anything about real markets, and without needing a paid key just to see how
  the mechanics work. Point it at your own real data (``op.csv_data(...)``)
  once you're past "how does this work" and into "does this actually hold".
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .alpha import AlphaCard

# optopsy requires Python >=3.12, one major version ahead of PaperPulse's own
# floor -- so this import can legitimately fail even with the extra installed
# on an older interpreter. Both cases (extra not installed, interpreter too
# old) degrade to the same friendly message rather than an ImportError.
try:
    import optopsy as op

    OPTOPSY_AVAILABLE = True
except ImportError:
    OPTOPSY_AVAILABLE = False

INSTALL_HINT = (
    "Backtesting needs the optopsy library (AGPL-3.0, a separate package -- "
    "not required for anything else in PaperPulse) and Python 3.12 or newer.\n"
    "Install with: pip install \"paperpulse[backtest]\""
)


@dataclass
class BacktestDemo:
    """The result of a demo backtest: what ran, and the honest caveats."""

    strategy: str
    csv_columns: dict[str, int]
    # pandas.DataFrame; typed as Any rather than pandas.DataFrame so this
    # module (and mypy on it) never needs pandas as a hard import -- optopsy
    # is what actually depends on pandas, and it's optional.
    aggregated: Any
    notes: list[str] = field(default_factory=list)


def _synthetic_chain(
    *, cycles: int = 2, dte: int = 60, seed: int = 7
) -> list[list]:
    """A small, clearly-fake SPX-shaped option chain.

    A backtest needs to price the *same contract* on both the day it's
    entered and the day it's exited, so this generates one quote per day for
    each of a handful of strikes across a full ``dte``-day expiration cycle
    (repeated ``cycles`` times back to back) -- not just an isolated snapshot.

    Column order matches optopsy's own sample data: underlying, type,
    expiration, quotedate, strike, bid, ask, delta. Delta uses the standard
    call/put sigmoid approximation and widens towards 0/1 as expiration nears,
    the way real time decay behaves; it is illustrative, not a real pricing
    model."""
    rng = random.Random(seed)
    spot = 4500.0
    day = date(2024, 1, 2)
    rows: list[list] = []

    for cycle_i in range(cycles):
        expiration = day + timedelta(days=dte)
        # A flat-drift market makes short-premium strategies like the iron
        # condor win every single trade, which teaches the wrong lesson.
        # Alternate a real trending cycle in so losing trades show up too --
        # an iron condor's short strikes get breached on a big enough move.
        drift = 6.0 if cycle_i % 2 else 0.0
        for d in range(dte + 1):  # inclusive of expiration day (DTE 0, the exit)
            quote_date = day + timedelta(days=d)
            spot += rng.uniform(-15, 15) + drift
            days_left = max(1, dte - d)
            for strike_offset in range(-16, 17):
                strike = round((spot + strike_offset * 50) / 5) * 5
                # Moneyness scaling grows as expiration approaches, mimicking
                # how delta migrates toward 0/1 near the money's resolution.
                time_scale = 22 * (dte / days_left) ** 0.5
                signed_moneyness = (strike - spot) / spot * time_scale
                call_delta = max(0.02, min(0.98, 1 / (1 + math.exp(signed_moneyness))))
                put_delta = max(-0.98, min(-0.02, call_delta - 1))
                distance = abs(strike - spot) / spot
                theta_decay = max(0.15, days_left / dte)
                # Time value alone (peaks at the money, decays with distance
                # and with days left) massively underprices deep ITM options,
                # which never costs the model anything to have breached a
                # short strike. Intrinsic value is what actually makes a
                # short strategy lose money on a big directional move.
                extrinsic = max(0.25, (1 - distance * 4) * spot * 0.02 * theta_decay)
                intrinsic_call = max(0.0, spot - strike)
                intrinsic_put = max(0.0, strike - spot)
                for option_type, delta, intrinsic in (
                    ("call", call_delta, intrinsic_call),
                    ("put", put_delta, intrinsic_put),
                ):
                    mid = intrinsic + extrinsic
                    spread = max(0.05, mid * 0.03)
                    rows.append(
                        [
                            "SPX",
                            option_type,
                            expiration.strftime("%m/%d/%Y"),
                            quote_date.strftime("%m/%d/%Y"),
                            strike,
                            round(mid - spread / 2, 2),
                            round(mid + spread / 2, 2),
                            round(delta, 2),
                        ]
                    )
        day = expiration + timedelta(days=1)  # next cycle starts fresh
    return rows


def _write_synthetic_csv(path: str, **kwargs) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for row in _synthetic_chain(**kwargs):
            writer.writerow(row)


# Column positions written by _synthetic_chain, for op.csv_data().
_COLUMNS = {
    "underlying_symbol": 0,
    "option_type": 1,
    "expiration": 2,
    "quote_date": 3,
    "strike": 4,
    "bid": 5,
    "ask": 6,
    "delta": 7,
}


def run_demo(card: AlphaCard | None = None) -> BacktestDemo:
    """Run a real optopsy backtest on synthetic data and return the result.

    ``card`` is used only for context in the notes (what the source paper
    claimed) -- the backtest itself always runs the same illustrative
    strategy, since a regex-extracted claim doesn't specify the strikes, DTE,
    or position sizing a real backtest needs. Raises ``RuntimeError`` with
    ``INSTALL_HINT`` if optopsy isn't available."""
    if not OPTOPSY_AVAILABLE:
        raise RuntimeError(INSTALL_HINT)

    import tempfile
    from pathlib import Path

    notes = [
        "Data: a small SYNTHETIC option chain generated for this demo -- not "
        "real market data, and not a test of any paper's specific claim.",
    ]
    if card is not None:
        if card.claim:
            notes.append(f"Source paper's claim: {card.claim}")
        if card.data_sources:
            notes.append(f"Source paper's own data: {', '.join(card.data_sources)}")
        if card.period:
            notes.append(f"Source paper's own period: {card.period}")

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = str(Path(tmp) / "synthetic_chain.csv")
        _write_synthetic_csv(csv_path)
        # Explicit kwargs, not **_COLUMNS: csv_data's real signature mixes int
        # column-index params with str|None date params, which mypy can't
        # verify against a plain dict[str, int] unpacked with **.
        data = op.csv_data(
            csv_path,
            underlying_symbol=_COLUMNS["underlying_symbol"],
            option_type=_COLUMNS["option_type"],
            expiration=_COLUMNS["expiration"],
            quote_date=_COLUMNS["quote_date"],
            strike=_COLUMNS["strike"],
            bid=_COLUMNS["bid"],
            ask=_COLUMNS["ask"],
            delta=_COLUMNS["delta"],
        )

        # Iron condor: the canonical multi-leg strategy, one delta target per
        # leg -- the clearest illustration of how optopsy actually selects
        # strikes and prices a position.
        aggregated = op.iron_condor(
            data,
            max_entry_dte=60,
            exit_dte=0,
            leg1_delta=op.TargetRange(target=0.15, min=0.05, max=0.30),
            leg2_delta=op.TargetRange(target=0.30, min=0.15, max=0.45),
            leg3_delta=op.TargetRange(target=0.30, min=0.15, max=0.45),
            leg4_delta=op.TargetRange(target=0.15, min=0.05, max=0.30),
        )

    if aggregated.empty:
        notes.append(
            "No trades matched these delta targets in the synthetic chain -- "
            "this can happen with small synthetic datasets; it is not a "
            "finding about the strategy."
        )

    return BacktestDemo(
        strategy="iron_condor",
        csv_columns=_COLUMNS,
        aggregated=aggregated,
        notes=notes,
    )


if __name__ == "__main__":  # smoke check (needs the backtest extra + Python 3.12+)
    rows = _synthetic_chain()
    assert len(rows) > 100, len(rows)
    assert all(len(r) == 8 for r in rows)
    assert {r[1] for r in rows} == {"call", "put"}
    print(f"synthetic chain OK: {len(rows)} rows")

    if OPTOPSY_AVAILABLE:
        demo = run_demo()
        assert demo.strategy == "iron_condor"
        print("run_demo OK:", len(demo.aggregated), "aggregated rows,", len(demo.notes), "notes")
    else:
        print("optopsy not installed here -- skipping the live run_demo() check")
