"""Relevance ranking.

Papers are scored by cosine similarity to the interest vector. On top of that
we apply Maximal Marginal Relevance (MMR) when selecting the top N, so the
digest doesn't hand you five near-identical papers -- it trades a little
relevance for variety, which is usually what you actually want to read.
"""

from __future__ import annotations

import numpy as np

from .embeddings import EmbeddingBackend
from .models import Paper, RankedPaper
from .profile import InterestProfile


def score_papers(
    papers: list[Paper],
    profile: InterestProfile,
    backend: EmbeddingBackend,
    *,
    avoid_vector: np.ndarray | None = None,
    avoid_weight: float = 0.5,
) -> tuple[list[float], np.ndarray]:
    """Return the relevance score for each paper and their embedding matrix.

    ``avoid_vector`` (from ``Config.avoid_topics``) is subtracted straight from
    the score -- unlike Rocchio feedback, this applies even to a cold-start
    profile that hasn't seen a single like/dislike yet."""
    if not papers:
        return [], np.zeros((0, profile.vector.shape[0]), dtype=np.float32)
    matrix = backend.encode([p.as_text() for p in papers])
    scores = matrix @ profile.vector
    if avoid_vector is not None:
        scores = scores - avoid_weight * (matrix @ avoid_vector)
    return scores.tolist(), matrix


def _mmr_select(
    scores: np.ndarray,
    matrix: np.ndarray,
    top_n: int,
    diversity: float,
) -> list[int]:
    """Greedy MMR. ``diversity`` in [0, 1]: 0 is pure relevance, 1 is pure
    novelty relative to what's already been picked."""
    remaining = list(range(len(scores)))
    selected: list[int] = []
    while remaining and len(selected) < top_n:
        if not selected:
            best = max(remaining, key=lambda i: scores[i])
        else:
            chosen = matrix[selected]

            def mmr_value(i: int) -> float:
                redundancy = float(np.max(chosen @ matrix[i]))
                return (1 - diversity) * scores[i] - diversity * redundancy

            best = max(remaining, key=mmr_value)
        selected.append(best)
        remaining.remove(best)
    return selected


def crowding_scores(matrix: np.ndarray, k: int = 3) -> np.ndarray:
    """For each row, the mean similarity to its ``k`` nearest *other* rows.

    High crowding means a paper sits in a dense neighbourhood of near-identical
    work in the same batch -- a proxy for "incremental". Returns zeros when the
    batch is too small to judge."""
    n = matrix.shape[0]
    if n < 2:
        return np.zeros(n, dtype=np.float32)
    sims = matrix @ matrix.T
    np.fill_diagonal(sims, -1.0)  # exclude self
    kk = min(k, n - 1)
    topk = np.sort(sims, axis=1)[:, -kk:]
    return topk.mean(axis=1)


def rank_papers(
    papers: list[Paper],
    profile: InterestProfile,
    backend: EmbeddingBackend,
    *,
    top_n: int = 5,
    diversity: float = 0.3,
    min_score: float = 0.0,
    avoid_vector: np.ndarray | None = None,
    avoid_weight: float = 0.5,
) -> list[RankedPaper]:
    """Rank ``papers`` and return the top ``top_n`` as ``RankedPaper``s.

    Each returned paper carries its ``crowding`` score for downstream trust
    signals."""
    scores, matrix = score_papers(
        papers, profile, backend, avoid_vector=avoid_vector, avoid_weight=avoid_weight
    )
    if not scores:
        return []

    scores_arr = np.asarray(scores)
    crowding = crowding_scores(matrix)
    order = _mmr_select(scores_arr, matrix, top_n, diversity)

    ranked = [
        RankedPaper(
            paper=papers[i],
            score=float(scores_arr[i]),
            crowding=float(crowding[i]),
        )
        for i in order
        if scores_arr[i] >= min_score
    ]
    return ranked
