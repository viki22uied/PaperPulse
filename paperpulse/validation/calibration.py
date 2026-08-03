"""Calibration metrics for the prospective flag-validation ledger.

Computes per-badge-tier hit rates, Brier scores, and reliability-diagram
data against realized outcomes.  Base-rate corrected: retraction is rare,
so raw accuracy is meaningless -- lift over base rate is what matters.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .ledger import ValidationLedger

_BADGE_ORDER = {"caution": 0, "mixed": 1, "clean": 2}


@dataclass
class CalibrationBucket:
    badge: str
    total: int = 0
    with_outcome: int = 0
    outcome_rate: float = 0.0
    brier: float = 0.0
    lift: float = 0.0


@dataclass
class CalibrationResult:
    buckets: list[CalibrationBucket] = field(default_factory=list)
    base_rate: float = 0.0
    total_papers: int = 0
    total_outcomes: int = 0
    outcome_types: dict[str, int] = field(default_factory=dict)


def calibration_report(
    ledger: ValidationLedger,
    *,
    outcome_filter: str | None = None,
) -> CalibrationResult:
    """Per-badge calibration against ground-truth outcomes.

    ``outcome_filter`` narrows to one outcome type (e.g. "retracted");
    None includes all outcomes.
    """
    all_ids = ledger.all_paper_ids()
    if not all_ids:
        return CalibrationResult()

    outcomes = ledger.outcomes_for(all_ids)

    if outcome_filter:
        outcomes = {
            pid: [o for o in outs if o["outcome"] == outcome_filter]
            for pid, outs in outcomes.items()
        }
        outcomes = {pid: outs for pid, outs in outcomes.items() if outs}

    badge_total: dict[str, int] = defaultdict(int)
    badge_hit: dict[str, int] = defaultdict(int)
    outcome_types: dict[str, int] = defaultdict(int)

    for pid in all_ids:
        badge = ledger.badge_for(pid)
        if badge is None:
            continue
        badge_total[badge] += 1
        paper_outcomes = outcomes.get(pid, [])
        if paper_outcomes:
            badge_hit[badge] += 1
            for o in paper_outcomes:
                outcome_types[o["outcome"]] += 1

    total = sum(badge_total.values())
    total_with_outcome = sum(badge_hit.values())
    base_rate = total_with_outcome / total if total else 0.0

    buckets: list[CalibrationBucket] = []
    for badge in sorted(badge_total, key=lambda b: _BADGE_ORDER.get(b, 99)):
        n = badge_total[badge]
        hits = badge_hit[badge]
        rate = hits / n if n else 0.0

        predicted_prob = {"caution": 0.7, "mixed": 0.4, "clean": 0.1}.get(badge, 0.5)
        brier = _brier_score(predicted_prob, rate, n)
        lift = (rate / base_rate) if base_rate > 0 else 0.0

        buckets.append(CalibrationBucket(
            badge=badge,
            total=n,
            with_outcome=hits,
            outcome_rate=round(rate, 4),
            brier=round(brier, 4),
            lift=round(lift, 2),
        ))

    return CalibrationResult(
        buckets=buckets,
        base_rate=round(base_rate, 4),
        total_papers=total,
        total_outcomes=total_with_outcome,
        outcome_types=dict(outcome_types),
    )


def _brier_score(predicted: float, observed_rate: float, n: int) -> float:
    if n == 0:
        return 0.0
    return (predicted - observed_rate) ** 2
