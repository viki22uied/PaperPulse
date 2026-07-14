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


@signal("subgroup_robustness")
def subgroup_robustness_signal(paper: Paper, **_) -> Signal:
    """Strong aggregate numbers can hide weak subgroups. Reward abstracts that
    report breakdowns; nudge those that only ever speak in averages."""
    if SUBGROUP_TERMS.search(paper.abstract):
        return Signal(
            "subgroup_robustness", OK, "Reports subgroup / robustness breakdowns."
        )
    if AGG_ONLY.search(paper.abstract):
        return Signal(
            "subgroup_robustness",
            WARN,
            "Only aggregate results mentioned; subgroup performance unclear.",
        )
    return Signal("subgroup_robustness", OK, "No aggregate-only red flag.")


@signal("metric_gaming")
def metric_gaming_signal(paper: Paper, **_) -> Signal:
    """Flag improvements framed around a metric with hints of marginal or
    post-hoc gains rather than a genuine underlying advance."""
    text = paper.abstract
    if METRIC_TERMS.search(text) and GAMING_TERMS.search(text):
        return Signal(
            "metric_gaming",
            WARN,
            "Metric gains described in marginal / post-hoc terms; check whether "
            "the improvement is within variance.",
        )
    return Signal("metric_gaming", OK, "No metric-gaming language detected.")


@signal("deployability")
def deployability_signal(paper: Paper, **_) -> Signal:
    """Flag assumptions that make a result hard to use in practice: oracle
    inputs, non-causal / look-ahead features, or extreme compute."""
    if DEPLOY_RED_FLAGS.search(paper.abstract):
        return Signal(
            "deployability",
            WARN,
            "Mentions assumptions that may not hold at inference (oracle inputs, "
            "look-ahead features, or very large compute).",
        )
    return Signal("deployability", OK, "No obvious deployability red flags.")


@signal("leakage")
def leakage_signal(paper: Paper, **_) -> Signal:
    """Random splits on temporal / financial data are a leakage classic."""
    text = paper.abstract
    if TIME_SERIES_TERMS.search(text) and LEAKAGE_TERMS.search(text):
        return Signal(
            "leakage",
            FLAG,
            "Random/k-fold splitting on time-series-like data risks lookahead "
            "leakage; a temporal split is usually required.",
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
        )
    return Signal("crowding", OK, f"Relatively distinct (crowding {crowding:.2f}).")


@signal("baseline_fairness")
def baseline_fairness_signal(paper: Paper, **_) -> Signal:
    """Wins over weak or outdated baselines are worth discounting."""
    if WEAK_BASELINE.search(paper.abstract):
        return Signal(
            "baseline_fairness",
            WARN,
            "Comparison may rely on a weak or outdated baseline.",
        )
    return Signal("baseline_fairness", OK, "No weak-baseline language detected.")
