"""Finance paper overfitting screener (Feature B).

Operationalizes DSR/PBO/Harvey-Liu logic as deterministic signals over the
alpha-card fields already extracted.  Flags papers that report suspiciously
high Sharpe/t-stats without disclosing trial counts, papers below the
factor-zoo hurdle (t > 3.0), and missing cost/survivorship/look-ahead
disclosures.

These are *screening* flags, not verdicts -- they identify papers that
deserve extra scrutiny before you trust the headline number.
"""

from __future__ import annotations

import re

from ..models import Paper
from . import FLAG, OK, WARN, Signal, signal

# Harvey-Liu-Zhu (2016): with 316+ factors tested, new factors should
# clear t > 3.0, not the naive 1.96.
_FACTOR_ZOO_HURDLE = 3.0

_TSTAT_RE = re.compile(
    r"\bt[- ]?(?:stat(?:istic)?s?|value)?\s*(?:of\s+|=\s*|:\s*)(-?\d+\.\d+)", re.I
)
_SHARPE_RE = re.compile(
    r"\bSharpe(?:\s+ratios?)?\s*(?:of\s+|=\s*|:\s*)?(\d+\.\d+)", re.I
)
_TRIALS_RE = re.compile(
    r"\b(\d+)\s*(?:strateg|specification|configuration|variant|model|"
    r"combination|signal|factor|portfolio|permutation)s?\b", re.I
)
_MULTIPLE_TESTING_RE = re.compile(
    r"\b(multiple\s+(?:testing|comparison|hypothes)|"
    r"Bonferroni|Holm|BH\b|Benjamini|family[- ]wise|"
    r"false\s+discovery|Romano|White.s?\s+reality|"
    r"bootstrap(?:ped)?\s+(?:p[- ]?value|reality))\b", re.I
)
_OOS_RE = re.compile(
    r"\b(out[- ]of[- ]sample|walk[- ]forward|live\s+trad|"
    r"paper\s+trad|real[- ]time|forward[- ]test|"
    r"holdout|validation\s+(?:set|period|sample))\b", re.I
)


@signal("factor_zoo_hurdle")
def factor_zoo_hurdle_signal(paper: Paper, **_) -> Signal:
    """Flag t-stats between 1.96 and 3.0 as below the Harvey-Liu
    multiple-testing hurdle for the 300+ factor zoo."""
    text = f"{paper.title} {paper.abstract}"
    matches = _TSTAT_RE.findall(text)
    if not matches:
        return Signal("factor_zoo_hurdle", OK, "No t-statistic reported.")

    tstats = [abs(float(t)) for t in matches]
    max_t = max(tstats)

    if max_t < 1.96:
        return Signal(
            "factor_zoo_hurdle", FLAG,
            f"Reported t-stat ({max_t:.2f}) is below the conventional 1.96 threshold.",
            evidence=f"t-stat {max_t:.2f}",
            confidence=0.8,
            weight=1.5,
        )
    if max_t < _FACTOR_ZOO_HURDLE:
        return Signal(
            "factor_zoo_hurdle", WARN,
            f"Reported t-stat ({max_t:.2f}) clears 1.96 but falls below the "
            f"Harvey-Liu factor-zoo hurdle of {_FACTOR_ZOO_HURDLE:.1f}, which "
            "accounts for the 300+ factors already tested in the literature.",
            evidence=f"t-stat {max_t:.2f} < {_FACTOR_ZOO_HURDLE:.1f}",
            confidence=0.7,
            weight=1.3,
        )
    return Signal(
        "factor_zoo_hurdle", OK,
        f"Reported t-stat ({max_t:.2f}) clears the factor-zoo hurdle.",
        evidence=f"t-stat {max_t:.2f}",
    )


@signal("deflation_gap")
def deflation_gap_signal(paper: Paper, **_) -> Signal:
    """Flag papers that report a Sharpe ratio or t-stat without disclosing
    the number of strategies/models tried.  Without a trial count, the
    reported stat can't be deflated for selection bias (Bailey & de Prado's
    Deflated Sharpe Ratio)."""
    text = f"{paper.title} {paper.abstract}"
    has_sharpe = _SHARPE_RE.search(text)
    has_tstat = _TSTAT_RE.search(text)
    if not has_sharpe and not has_tstat:
        return Signal("deflation_gap", OK, "No Sharpe/t-stat to deflate.")

    has_trials = _TRIALS_RE.search(text)
    has_correction = _MULTIPLE_TESTING_RE.search(text)

    if has_trials or has_correction:
        return Signal(
            "deflation_gap", OK,
            "Reports trial count or multiple-testing correction.",
            evidence=(has_trials or has_correction).group(0),
        )

    metric = has_sharpe or has_tstat
    return Signal(
        "deflation_gap", WARN,
        "Reports a Sharpe ratio or t-stat with no disclosed trial count "
        "and no multiple-testing correction.  The headline number cannot "
        "be deflated for selection bias (DSR/PBO framework).",
        evidence=metric.group(0) if metric else "",
        confidence=0.65,
        weight=1.3,
    )


@signal("no_oos_validation")
def no_oos_validation_signal(paper: Paper, **_) -> Signal:
    """Flag finance papers with quantitative claims but no mention of
    out-of-sample, walk-forward, or holdout validation."""
    text = f"{paper.title} {paper.abstract}"
    has_sharpe = _SHARPE_RE.search(text)
    has_tstat = _TSTAT_RE.search(text)
    if not has_sharpe and not has_tstat:
        return Signal("no_oos_validation", OK, "No quantitative claim to validate.")

    if _OOS_RE.search(text):
        return Signal(
            "no_oos_validation", OK,
            "Mentions out-of-sample or validation methodology.",
        )

    return Signal(
        "no_oos_validation", WARN,
        "Reports quantitative results with no mention of out-of-sample "
        "validation, walk-forward testing, or a holdout period.",
        evidence=(has_sharpe or has_tstat).group(0) if (has_sharpe or has_tstat) else "",
        confidence=0.6,
        weight=1.2,
    )
