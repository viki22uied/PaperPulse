"""Contradiction mapping across a batch of papers.

``contradiction_map`` finds pairs of papers that are topically close (high
embedding similarity) yet express opposing sentiment about their results. That
combination is a decent proxy for "these two disagree", worth surfacing as a
place to look, not a proven contradiction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .embeddings import EmbeddingBackend
from .models import Paper

_POSITIVE = re.compile(
    r"\b(improv\w*|outperform\w*|gain\w*|effective|benefit\w*|superior|better|"
    r"increase\w*|boost\w*|success\w*)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(fail\w*|worse|degrad\w*|no (significant )?(improvement|benefit|gain)|"
    r"does not|cannot|ineffective|overestimate\w*|contrary|refut\w*|"
    r"contradict\w*|myth|illusion|question\w*)\b",
    re.I,
)


def _polarity(text: str) -> int:
    """Crude sentiment of a claim: +1 positive, -1 negative, 0 neutral."""
    return len(_POSITIVE.findall(text)) - len(_NEGATIVE.findall(text))


@dataclass
class ContradictionPair:
    a: Paper
    b: Paper
    similarity: float
    note: str
    # Sign of each side's claim (+1/-1). A pair only forms when these oppose,
    # so the *assignment* is what a diff compares: if `a` was the positive side
    # last run and is the negative side now, the disagreement has flipped.
    polarity_a: int = 0
    polarity_b: int = 0


def contradiction_map(
    papers: list[Paper],
    backend: EmbeddingBackend,
    *,
    similarity_threshold: float = 0.6,
    max_pairs: int = 20,
) -> list[ContradictionPair]:
    """Return candidate contradicting pairs, most similar first."""
    if len(papers) < 2:
        return []
    matrix = backend.encode([p.as_text() for p in papers])
    sims = matrix @ matrix.T
    polarities = [_polarity(p.abstract) for p in papers]

    pairs: list[ContradictionPair] = []
    for i in range(len(papers)):
        for j in range(i + 1, len(papers)):
            sim = float(sims[i, j])
            if sim < similarity_threshold:
                continue
            pi, pj = polarities[i], polarities[j]
            if pi * pj < 0:  # opposite sign => opposing claims
                pairs.append(
                    ContradictionPair(
                        a=papers[i],
                        b=papers[j],
                        similarity=sim,
                        note="Closely related but express opposing outcomes.",
                        polarity_a=1 if pi > 0 else -1,
                        polarity_b=1 if pj > 0 else -1,
                    )
                )
    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs[:max_pairs]
