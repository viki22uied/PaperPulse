"""Quant-desk-inspired trust signals.

These mirror the discipline of systematic alpha research: is the "edge" real or
a cosmetic rehash, does it survive subgroups, is it gaming a metric, is it
actually deployable? All are abstract-level heuristics -- cheap tripwires, not
audits.
"""

from __future__ import annotations

import re

from ..models import Paper
from . import FLAG, OK, WARN, Signal, signal

SUBGROUP_TERMS = re.compile(
    r"\b(subgroup|per[- ]class|breakdown|stratif\w*|across (datasets|domains|"
    r"languages|tasks)|out[- ]of[- ]distribution|ood|worst[- ]case|"
    r"tail|robustness)\b",
    re.I,
)
AGG_ONLY = re.compile(r"\b(on average|overall|aggregate|mean)\b", re.I)

METRIC_TERMS = re.compile(
    r"\b(accuracy|f1|bleu|rouge|auc|map|ndcg|perplexity|sharpe|score)\b", re.I
)
GAMING_TERMS = re.compile(
    r"\b(post[- ]?hoc|cherry[- ]?pick\w*|by (\d+(\.\d+)?)\s*(points?|%)|"
    r"marginal(ly)?|within (noise|variance))\b",
    re.I,
)

DEPLOY_RED_FLAGS = re.compile(
    r"\b(oracle|ground[- ]truth at (inference|test)|future information|"
    r"look[- ]ahead|non[- ]causal|assumes? access to|requires? (\d+)\s*gpus?|"
    r"tens? of thousands of gpu|hundreds of gpus)\b",
    re.I,
)

LEAKAGE_TERMS = re.compile(
    r"\b(random(ly)? split|shuffle\w* split|k[- ]?fold)\b", re.I
)
TIME_SERIES_TERMS = re.compile(
    r"\b(time[- ]series|forecast\w*|temporal|stock|price|market|trading|"
    r"financial|returns?)\b",
    re.I,
)

WEAK_BASELINE = re.compile(
    r"\b(compared? (only )?(to|with) (a )?(simple|weak|naive|vanilla) baseline|"
    r"without comparison|no baseline|against an? older)\b",
    re.I,
)

BACKTEST_TERMS = re.compile(
    r"\b(backtest\w*|historical (data|returns?|prices?)|in[- ]sample)\b", re.I
)
OUT_OF_SAMPLE_TERMS = re.compile(
    r"\b(out[- ]of[- ]sample|walk[- ]forward|live trading|paper trading|"
    r"transaction costs?|slippage)\b",
    re.I,
)

TRADING_STRATEGY_TERMS = re.compile(
    r"\b(trading strategy|trading rule|portfolio strategy|long[- /]short|"
    r"alpha (signal|strategy))\b",
    re.I,
)
SURVIVORSHIP_TERMS = re.compile(
    r"\b(surviv\w*|delist\w*|bankrupt\w*|dead firms?)\b", re.I
)
COST_TERMS = re.compile(
    r"\b(transaction costs?|slippage|trading costs?|market impact|commission\w*)\b",
    re.I,
)
CROSS_REGIME_TERMS = re.compile(
    r"\b(multiple (markets|periods|regimes)|across (markets|regions|"
    r"time periods|asset classes|cycles)|robust\w* across|"
    r"out[- ]of[- ]sample periods?|different (market )?regimes?)\b",
    re.I,
)


@signal("subgroup_robustness")
def subgroup_robustness_signal(paper: Paper, **_) -> Signal:
    """Strong aggregate numbers can hide weak subgroups. Reward abstracts that
    report breakdowns; nudge those that only ever speak in averages."""
    match = SUBGROUP_TERMS.search(paper.abstract)
    if match:
        return Signal(
            "subgroup_robustness", OK, "Reports subgroup / robustness breakdowns.",
            evidence=match.group(0),
        )
    agg = AGG_ONLY.search(paper.abstract)
    if agg:
        return Signal(
            "subgroup_robustness",
            WARN,
            "Only aggregate results mentioned; subgroup performance unclear.",
            evidence=agg.group(0),
            confidence=0.45,
        )
    return Signal("subgroup_robustness", OK, "No aggregate-only red flag.")


@signal("metric_gaming")
def metric_gaming_signal(paper: Paper, **_) -> Signal:
    """Flag improvements framed around a metric with hints of marginal or
    post-hoc gains rather than a genuine underlying advance."""
    text = paper.abstract
    metric = METRIC_TERMS.search(text)
    gaming = GAMING_TERMS.search(text)
    if metric and gaming:
        return Signal(
            "metric_gaming",
            WARN,
            "Metric gains described in marginal / post-hoc terms; check whether "
            "the improvement is within variance.",
            evidence=f"{metric.group(0)} … {gaming.group(0)}",
            confidence=0.55,
        )
    return Signal("metric_gaming", OK, "No metric-gaming language detected.")


@signal("deployability")
def deployability_signal(paper: Paper, **_) -> Signal:
    """Flag assumptions that make a result hard to use in practice: oracle
    inputs, non-causal / look-ahead features, or extreme compute."""
    match = DEPLOY_RED_FLAGS.search(paper.abstract)
    if match:
        return Signal(
            "deployability",
            WARN,
            "Mentions assumptions that may not hold at inference (oracle inputs, "
            "look-ahead features, or very large compute).",
            evidence=match.group(0),
            confidence=0.6,
        )
    return Signal("deployability", OK, "No obvious deployability red flags.")


@signal("leakage")
def leakage_signal(paper: Paper, **_) -> Signal:
    """Random splits on temporal / financial data are a leakage classic."""
    text = paper.abstract
    ts = TIME_SERIES_TERMS.search(text)
    split = LEAKAGE_TERMS.search(text)
    if ts and split:
        return Signal(
            "leakage",
            FLAG,
            "Random/k-fold splitting on time-series-like data risks lookahead "
            "leakage; a temporal split is usually required.",
            evidence=f"{ts.group(0)} + {split.group(0)}",
            confidence=0.75,
        )
    return Signal("leakage", OK, "No obvious train/test leakage pattern.")


@signal("crowding")
def crowding_signal(paper: Paper, *, crowding: float | None = None, **_) -> Signal:
    """Novelty-vs-crowding. ``crowding`` (supplied by the ranker) is the mean
    similarity to this paper's nearest neighbours in the same batch; a very
    crowded neighbourhood suggests an incremental entry in a busy area."""
    if crowding is None:
        return Signal("crowding", OK, "Crowding not evaluated.")
    if crowding >= 0.85:
        return Signal(
            "crowding",
            WARN,
            f"Very similar to other papers in the batch (crowding {crowding:.2f}); "
            "likely incremental.",
            evidence=f"crowding {crowding:.2f}",
            confidence=0.5,
        )
    return Signal("crowding", OK, f"Relatively distinct (crowding {crowding:.2f}).")


@signal("literature_novelty")
def literature_novelty_signal(
    paper: Paper, *, literature_crowding: float | None = None, **_
) -> Signal:
    """Novelty vs. the *known literature* (E2), not just today's batch --
    ``literature_crowding`` (supplied by the pipeline) is the paper's max
    cosine similarity to a fixed reference set of canonical factor papers
    plus anything logged in the known/tried topics store."""
    if literature_crowding is None:
        return Signal("literature_novelty", OK, "Literature novelty not evaluated.")
    if literature_crowding >= 0.5:
        return Signal(
            "literature_novelty",
            WARN,
            f"Very similar to well-known factor literature (similarity "
            f"{literature_crowding:.2f}); may be a rehash of an established "
            "factor rather than a genuinely new data source.",
            evidence=f"literature similarity {literature_crowding:.2f}",
            confidence=0.5,
        )
    return Signal(
        "literature_novelty", OK,
        f"Distinct from known factor literature (similarity {literature_crowding:.2f}).",
    )


@signal("backtest_overfit")
def backtest_overfit_signal(paper: Paper, **_) -> Signal:
    """Backtested returns without an out-of-sample or cost-aware check are the
    classic quant-strategy overfitting tell."""
    text = paper.abstract
    match = BACKTEST_TERMS.search(text)
    if match and not OUT_OF_SAMPLE_TERMS.search(text):
        return Signal(
            "backtest_overfit",
            WARN,
            "Backtested/historical results with no mention of an out-of-sample, "
            "walk-forward, or transaction-cost check; may be overfit to the "
            "backtest window.",
            evidence=match.group(0),
            confidence=0.6,
        )
    return Signal("backtest_overfit", OK, "No backtest-only red flag.")


@signal("survivorship_bias")
def survivorship_bias_signal(paper: Paper, **_) -> Signal:
    """Backtests that never mention delisted/failed firms are a classic
    survivorship-bias tell -- the sample quietly excludes the losers."""
    text = paper.abstract
    if BACKTEST_TERMS.search(text) and not SURVIVORSHIP_TERMS.search(text):
        return Signal(
            "survivorship_bias",
            WARN,
            "Backtest with no mention of delisted/failed firms; sample may "
            "suffer from survivorship bias.",
            evidence=BACKTEST_TERMS.search(text).group(0),
            confidence=0.5,
        )
    return Signal("survivorship_bias", OK, "No survivorship-bias red flag.")


@signal("transaction_cost_omission")
def transaction_cost_omission_signal(paper: Paper, **_) -> Signal:
    """A trading strategy with no mention of costs/slippage may look
    profitable purely because costs were never modeled."""
    text = paper.abstract
    match = TRADING_STRATEGY_TERMS.search(text)
    if match and not COST_TERMS.search(text):
        return Signal(
            "transaction_cost_omission",
            WARN,
            "Trading strategy with no mention of transaction costs or "
            "slippage; reported profitability may not survive real costs.",
            evidence=match.group(0),
            confidence=0.55,
        )
    return Signal("transaction_cost_omission", OK, "No transaction-cost red flag.")


@signal("single_market_period")
def single_market_period_signal(paper: Paper, **_) -> Signal:
    """A backtest or strategy tested on one market/period with no mention of
    robustness across regimes risks being an artifact of that window."""
    text = paper.abstract
    match = BACKTEST_TERMS.search(text) or TRADING_STRATEGY_TERMS.search(text)
    if match and not CROSS_REGIME_TERMS.search(text):
        return Signal(
            "single_market_period",
            WARN,
            "No mention of testing across multiple markets, periods, or "
            "regimes; result may be specific to a single window.",
            evidence=match.group(0),
            confidence=0.45,
        )
    return Signal("single_market_period", OK, "No single-market/period red flag.")


@signal("baseline_fairness")
def baseline_fairness_signal(paper: Paper, **_) -> Signal:
    """Wins over weak or outdated baselines are worth discounting."""
    match = WEAK_BASELINE.search(paper.abstract)
    if match:
        return Signal(
            "baseline_fairness",
            WARN,
            "Comparison may rely on a weak or outdated baseline.",
            evidence=match.group(0),
            confidence=0.55,
        )
    return Signal("baseline_fairness", OK, "No weak-baseline language detected.")
