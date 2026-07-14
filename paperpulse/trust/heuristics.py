"""Text-pattern trust signals over the title/abstract (and full text if present)."""

from __future__ import annotations

import re

from ..models import Paper
from . import FLAG, OK, WARN, Signal, signal

STRONG_CLAIMS = re.compile(
    r"\b(state[- ]of[- ]the[- ]art|sota|outperform\w*|significantly|"
    r"substantial\w*|dramatic\w*|novel|first\s+to|best|superior|"
    r"unprecedented|breakthrough)\b",
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


@signal("evidence")
def evidence_signal(paper: Paper, **_) -> Signal:
    """Strong claims should come with numbers."""
    text = paper.abstract
    claims = len(STRONG_CLAIMS.findall(text))
    has_numbers = bool(NUMERIC_EVIDENCE.search(text))
    if claims >= 2 and not has_numbers:
        return Signal(
            "evidence",
            FLAG,
            "Strong claims but no quantified results, error bars, or "
            "significance in the abstract.",
        )
    if claims >= 1 and not has_numbers:
        return Signal("evidence", WARN, "Makes a claim without numbers in the abstract.")
    return Signal("evidence", OK, "Claims are backed by quantitative detail.")


@signal("overclaim")
def overclaim_signal(paper: Paper, **_) -> Signal:
    """All-assertive, zero-hedge abstracts are the classic overclaiming tell."""
    text = paper.abstract
    strong = len(STRONG_CLAIMS.findall(text))
    hedged = len(HEDGES.findall(text))
    if strong >= 3 and hedged == 0:
        return Signal("overclaim", FLAG, f"{strong} assertive claim words and no hedging.")
    if strong >= 2 and hedged == 0:
        return Signal("overclaim", WARN, "Assertive framing with no hedging.")
    return Signal("overclaim", OK, "Claim language looks measured.")


@signal("reproducibility")
def reproducibility_signal(paper: Paper, *, full_text: str | None = None, **_) -> Signal:
    """Does the paper point to code or data?"""
    haystack = paper.abstract + (full_text or "")
    if CODE_DATA.search(haystack):
        return Signal("reproducibility", OK, "Mentions available code or data.")
    return Signal(
        "reproducibility", WARN, "No mention of released code or data."
    )


@signal("saturation")
def saturation_signal(paper: Paper, **_) -> Signal:
    """SOTA-on-a-benchmark claims deserve a second look."""
    if BENCHMARK_HYPE.search(paper.abstract):
        return Signal(
            "saturation",
            WARN,
            "Leads with a new-SOTA claim; check the margin and whether the "
            "benchmark is near ceiling.",
        )
    return Signal("saturation", OK, "No benchmark-chasing framing.")
