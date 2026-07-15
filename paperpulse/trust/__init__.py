"""Trust / signal-quality assessment.

These are *triage* signals, not verdicts. Working from a title and abstract (and
optionally full text and batch context), we flag patterns that correlate with
weaker or over-claimed work, so you know which papers to read skeptically. Every
signal is deterministic and explains itself, and the aggregate score is
deliberately conservative -- never presented as a quality guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..models import Paper

OK = "ok"
WARN = "warn"
FLAG = "flag"

_PENALTY = {OK: 0.0, WARN: 0.5, FLAG: 1.0}


@dataclass
class Signal:
    name: str
    status: str  # OK | WARN | FLAG
    note: str
    weight: float = 1.0
    evidence: str = ""       # exact text that triggered the flag (explainability)
    confidence: float = 1.0  # how reliable this heuristic's call is, 0-1


@dataclass
class TrustReport:
    signals: list[Signal] = field(default_factory=list)
    score: float = 1.0

    @property
    def flags(self) -> list[Signal]:
        return [s for s in self.signals if s.status != OK]

    @property
    def badge(self) -> str:
        # Any hard flag keeps a paper out of "clean", regardless of how high the
        # aggregate score is -- a single leakage red flag matters more than it
        # dilutes across ten signals.
        has_hard_flag = any(s.status == FLAG for s in self.signals)
        if self.score >= 0.75 and not has_hard_flag:
            return "clean"
        if self.score >= 0.45:
            return "mixed"
        return "caution"


# Signal context passed to every signal function as keyword args. Signals take
# what they need and ignore the rest via **_.
@dataclass
class SignalContext:
    crowding: float | None = None
    full_text: str | None = None
    online: bool = False
    # Loaded once per digest run (not per paper) from the configured topics DB.
    topics: list | None = None


SignalFn = Callable[..., Signal]
_REGISTRY: dict[str, SignalFn] = {}


def signal(name: str) -> Callable[[SignalFn], SignalFn]:
    def wrap(fn: SignalFn) -> SignalFn:
        _REGISTRY[name] = fn
        return fn

    return wrap


def registered() -> list[str]:
    return list(_REGISTRY)


# Import signal modules for their registration side effects.
from . import heuristics  # noqa: E402,F401
from . import quant  # noqa: E402,F401
from . import publication  # noqa: E402,F401
from . import external  # noqa: E402,F401
from . import known_topics  # noqa: E402,F401
from . import results  # noqa: E402,F401


DEFAULT_SIGNALS = [
    "evidence",
    "overclaim",
    "reproducibility",
    "saturation",
    "crowding",
    "subgroup_robustness",
    "metric_gaming",
    "deployability",
    "leakage",
    "baseline_fairness",
    "backtest_overfit",
    "peer_review",
    "known_topic",
    "weak_result",
]


def assess(
    paper: Paper,
    *,
    enabled: list[str] | None = None,
    context: SignalContext | None = None,
) -> TrustReport:
    """Run the enabled signals over a paper and aggregate into a report."""
    names = enabled if enabled is not None else DEFAULT_SIGNALS
    ctx = context or SignalContext()
    kwargs = {
        "crowding": ctx.crowding,
        "full_text": ctx.full_text,
        "online": ctx.online,
        "topics": ctx.topics,
    }

    signals: list[Signal] = []
    for name in names:
        fn = _REGISTRY.get(name)
        if fn is None:
            continue
        try:
            signals.append(fn(paper, **kwargs))
        except Exception:
            # A misbehaving signal must never sink the whole digest.
            signals.append(Signal(name, OK, "Signal skipped (error)."))

    total_weight = sum(s.weight for s in signals) or 1.0
    penalty = sum(_PENALTY[s.status] * s.weight for s in signals) / total_weight
    return TrustReport(signals=signals, score=round(1.0 - penalty, 3))


__all__ = [
    "OK",
    "WARN",
    "FLAG",
    "Signal",
    "TrustReport",
    "SignalContext",
    "assess",
    "registered",
    "DEFAULT_SIGNALS",
]
