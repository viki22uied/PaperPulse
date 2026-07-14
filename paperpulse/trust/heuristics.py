"""Text-pattern trust signals over the title/abstract (and full text if present)."""

from __future__ import annotations

import re

from ..models import Paper
from . import FLAG, OK, WARN, Signal, signal

STRONG_CLAIMS = re.compile(
    r"\b(state[- ]of[- ]the[- ]art|sota|outperform\w*|significantly|"
    r"substantial\w*|dramatic\w*|novel|first\s+to|best|superior|"
    r"unprecedented|breakthrough|"
    r"alpha[- ]generating|market[- ]beating|risk[- ]free|guarantee\w*|"
    r"consistently profitable|outsized returns?)\b",
    re.I,
)
HEDGES = re.compile(
    r"\b(suggest\w*|indicate\w*|may|might|could|preliminary|potential\w*|"
    r"appears?\s+to|we\s+hypothesi[sz]e|limitation)\b",
    re.I,
)
NUMERIC_EVIDENCE = re.compile(
    r"(\d+(\.\d+)?\s*%|\bp\s*[<=>]\s*0?\.\d+|±|\bstd\b|standard deviation|"
    r"confidence interval|\bci\b|error bars?|\bstatistical(ly)? signif)",
    re.I,
)
CODE_DATA = re.compile(
    r"\b(github\.com|gitlab|code (is|will be) (available|released)|"
    r"we release|open[- ]sourc\w*|publicly available|"
    r"available at|dataset is available|reproduc\w*)\b",
    re.I,
)
BENCHMARK_HYPE = re.compile(
    r"\b(new state[- ]of[- ]the[- ]art|new sota|sets? a new|achiev\w* sota|"
    r"tops? the leaderboard)\b",
    re.I,
)


def _phrases(matches: list[str], limit: int = 4) -> str:
    """De-duplicated, comma-joined sample of matched phrases for evidence."""
    seen: list[str] = []
    for m in matches:
        low = m.lower()
        if low not in [s.lower() for s in seen]:
            seen.append(m)
    return ", ".join(seen[:limit])


@signal("evidence")
def evidence_signal(paper: Paper, **_) -> Signal:
    """Strong claims should come with numbers."""
    text = paper.abstract
    claims = STRONG_CLAIMS.findall(text)
    has_numbers = bool(NUMERIC_EVIDENCE.search(text))
    ev = _phrases(claims)
    if len(claims) >= 2 and not has_numbers:
        return Signal(
            "evidence",
            FLAG,
            "Strong claims but no quantified results, error bars, or "
            "significance in the abstract.",
            evidence=ev,
            confidence=0.7,
        )
    if len(claims) >= 1 and not has_numbers:
        return Signal(
            "evidence", WARN, "Makes a claim without numbers in the abstract.",
            evidence=ev, confidence=0.55,
        )
    return Signal("evidence", OK, "Claims are backed by quantitative detail.")


@signal("overclaim")
def overclaim_signal(paper: Paper, **_) -> Signal:
    """All-assertive, zero-hedge abstracts are the classic overclaiming tell."""
    text = paper.abstract
    strong = STRONG_CLAIMS.findall(text)
    hedged = len(HEDGES.findall(text))
    ev = _phrases(strong)
    if len(strong) >= 3 and hedged == 0:
        return Signal(
            "overclaim", FLAG, f"{len(strong)} assertive claim words and no hedging.",
            evidence=ev, confidence=0.65,
        )
    if len(strong) >= 2 and hedged == 0:
        return Signal(
            "overclaim", WARN, "Assertive framing with no hedging.",
            evidence=ev, confidence=0.5,
        )
    return Signal("overclaim", OK, "Claim language looks measured.")


@signal("reproducibility")
def reproducibility_signal(paper: Paper, *, full_text: str | None = None, **_) -> Signal:
    """Does the paper point to code or data?"""
    haystack = paper.abstract + (full_text or "")
    match = CODE_DATA.search(haystack)
    if match:
        return Signal(
            "reproducibility", OK, "Mentions available code or data.",
            evidence=match.group(0),
        )
    # Absence of a keyword is weaker evidence than a positive match, so confidence
    # is deliberately low -- the code may simply not be named in the abstract.
    return Signal(
        "reproducibility", WARN, "No mention of released code or data.",
        confidence=0.4,
    )


@signal("saturation")
def saturation_signal(paper: Paper, **_) -> Signal:
    """SOTA-on-a-benchmark claims deserve a second look."""
    match = BENCHMARK_HYPE.search(paper.abstract)
    if match:
        return Signal(
            "saturation",
            WARN,
            "Leads with a new-SOTA claim; check the margin and whether the "
            "benchmark is near ceiling.",
            evidence=match.group(0),
            confidence=0.6,
        )
    return Signal("saturation", OK, "No benchmark-chasing framing.")
