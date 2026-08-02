"""JSON-shape serialization for a digest result.

Shared by the REST API (``api.py``) and the CLI's ``--format json`` so a
script piping ``paperpulse run --format json`` into ``jq`` sees exactly the
same shape a dashboard client fetching ``GET /api/digest`` does -- one
definition of "what a ranked paper looks like as JSON", not two that drift.
"""

from __future__ import annotations

from typing import Any

from .models import RankedPaper
from .pipeline import DigestResult


def paper_to_dict(item: RankedPaper, *, market_quotes: list[dict] | None = None) -> dict[str, Any]:
    paper = item.paper
    return {
        "id": paper.id,
        "title": paper.title,
        "score": round(item.score, 4),
        "priority": round(
            max(0.0, item.score) * (item.trust.score if item.trust else 1.0), 4
        ),
        "summary": item.summary,
        "regions": item.regions,
        "region_note": item.region_note or None,
        "why_rank": item.why_rank or None,
        "url": paper.url,
        "pdf_url": paper.pdf_url or None,
        "authors": paper.authors,
        "categories": paper.categories,
        "quotes": market_quotes or [],
        "alpha": None
        if item.alpha is None
        else {
            "testability": item.alpha.testability,
            "score": item.alpha.testability_score,
            "claim": item.alpha.claim,
            "effects": item.alpha.effects,
            "data_sources": item.alpha.data_sources,
            "universe": item.alpha.universe,
            "period": item.alpha.period,
            "missing": item.alpha.missing,
            "from_full_text": item.alpha.from_full_text,
        },
        "trust": None
        if item.trust is None
        else {
            "score": item.trust.score,
            "badge": item.trust.badge,
            "flags": [
                {
                    "name": s.name, "status": s.status, "note": s.note,
                    "evidence": s.evidence, "confidence": s.confidence,
                }
                for s in item.trust.flags
            ],
            "hygiene_notes": [
                {"name": s.name, "note": s.note} for s in item.trust.hygiene_notes
            ],
        },
    }


def digest_to_dict(
    result: DigestResult, *, include_market_quotes: bool = False
) -> dict[str, Any]:
    """``include_market_quotes`` is opt-in: it's a live network lookup per
    paper (ticker prices for finance papers), useful for the interactive
    dashboard but unwanted latency/network dependency for a script that just
    wants the ranked/scored data fast (``paperpulse run --format json``)."""
    quotes_by_id: dict[str, list[dict]] = {}
    if include_market_quotes:
        from . import market

        for item in result.ranked:
            quotes_by_id[item.paper.id] = market.enrich(
                f"{item.paper.title} {item.paper.abstract}"
            )

    return {
        "papers": [
            paper_to_dict(item, market_quotes=quotes_by_id.get(item.paper.id))
            for item in result.ranked
        ],
        "contradictions": [
            {"a": p.a.id, "b": p.b.id, "similarity": round(p.similarity, 3)}
            for p in result.contradictions
        ],
    }


__all__ = ["paper_to_dict", "digest_to_dict"]
