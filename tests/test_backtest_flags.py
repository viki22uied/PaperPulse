"""E1: backtest methodology red flags, each its own named signal."""

from paperpulse import trust
from paperpulse.models import Paper


def _paper(abstract):
    return Paper(id="1", title="t", abstract=abstract)


def test_survivorship_bias_flagged_without_mention():
    paper = _paper("We backtest the strategy using historical prices from 2000-2020.")
    assert trust.assess(paper, enabled=["survivorship_bias"]).signals[0].status == trust.WARN


def test_survivorship_bias_ok_when_mentioned():
    paper = _paper(
        "We backtest the strategy using historical prices, including delisted "
        "and bankrupt firms to avoid survivorship bias."
    )
    assert trust.assess(paper, enabled=["survivorship_bias"]).signals[0].status == trust.OK


def test_transaction_cost_omission_flagged():
    paper = _paper("We propose a long-short trading strategy with strong backtested returns.")
    assert trust.assess(paper, enabled=["transaction_cost_omission"]).signals[0].status == trust.WARN


def test_transaction_cost_omission_ok_when_costs_mentioned():
    paper = _paper(
        "We propose a long-short trading strategy and report returns net of "
        "transaction costs and slippage."
    )
    assert trust.assess(paper, enabled=["transaction_cost_omission"]).signals[0].status == trust.OK


def test_single_market_period_flagged():
    paper = _paper("We backtest the strategy on historical S&P 500 data from 2010-2015.")
    assert trust.assess(paper, enabled=["single_market_period"]).signals[0].status == trust.WARN


def test_single_market_period_ok_when_cross_regime_mentioned():
    paper = _paper(
        "We backtest the strategy across multiple markets and time periods to "
        "check robustness across regimes."
    )
    assert trust.assess(paper, enabled=["single_market_period"]).signals[0].status == trust.OK


def test_signals_are_independent_of_generic_backtest_overfit():
    # A clean paper on out-of-sample testing shouldn't trip the *new* flags
    # just because it mentions backtesting -- each needs its own missing term.
    paper = _paper(
        "We backtest a long-short strategy across multiple markets and "
        "periods, report out-of-sample results net of transaction costs and "
        "slippage, and exclude delisted firms to avoid survivorship bias."
    )
    report = trust.assess(
        paper,
        enabled=[
            "backtest_overfit", "survivorship_bias",
            "transaction_cost_omission", "single_market_period",
        ],
    )
    assert report.flags == []
