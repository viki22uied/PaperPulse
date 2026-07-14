"""bioRxiv / medRxiv source, via the public Cold Spring Harbor API.

Docs: https://api.biorxiv.org/. The ``details`` endpoint returns recent
preprints as JSON; we filter client-side by category keywords since the API
groups by broad server rather than arXiv-style tags.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..models import Paper
from .base import Query, register

API_TEMPLATE = "https://api.biorxiv.org/details/{server}/{start_date}/{end_date}/{cursor}"


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _record_to_paper(rec: dict, server: str) -> Paper:
    doi = rec.get("doi", "")
    return Paper(
        id=f"{server}:{doi}" if doi else rec.get("title", "")[:40],
        title=" ".join((rec.get("title") or "").split()),
        abstract=" ".join((rec.get("abstract") or "").split()),
        authors=[a.strip() for a in (rec.get("authors") or "").split(";") if a.strip()],
        categories=[rec.get("category", server)],
        published=_parse_date(rec.get("date")),
        url=f"https://doi.org/{doi}" if doi else "",
        pdf_url=f"https://www.{server}.org/content/{doi}v1.full.pdf" if doi else "",
    )


def fetch_recent(
    server: str = "biorxiv",
    *,
    start_date: str,
    end_date: str,
    max_results: int = 200,
    timeout: float = 30.0,
) -> list[Paper]:
    """Page through the bioRxiv details endpoint between two ``YYYY-MM-DD`` dates."""
    papers: list[Paper] = []
    cursor = 0
    while len(papers) < max_results:
        url = API_TEMPLATE.format(
            server=server, start_date=start_date, end_date=end_date, cursor=cursor
        )
        request = urllib.request.Request(
            url, headers={"User-Agent": "PaperPulse/0.1"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        collection = payload.get("collection", [])
        if not collection:
            break
        papers.extend(_record_to_paper(rec, server) for rec in collection)
        cursor += len(collection)
        if len(collection) < 100:
            break
    return papers[:max_results]


class BiorxivSource:
    """Recent-preprint adapter for bioRxiv/medRxiv.

    ``Query.categories`` is used to narrow by preprint category (case-insensitive
    substring match). Use category values like ``biorxiv`` or ``medrxiv`` to pick
    the server; anything else is treated as a category filter.
    """

    name = "biorxiv"

    def __init__(self, window_days: int = 3):
        self.window_days = window_days

    def fetch(self, query: Query) -> list[Paper]:
        from datetime import date, timedelta

        servers = [c for c in query.categories if c in {"biorxiv", "medrxiv"}] or [
            "biorxiv"
        ]
        filters = [c.lower() for c in query.categories if c not in {"biorxiv", "medrxiv"}]
        end = date.today()
        start = end - timedelta(days=self.window_days)

        results: list[Paper] = []
        for server in servers:
            batch = fetch_recent(
                server,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                max_results=query.max_results,
            )
            if filters:
                batch = [
                    p
                    for p in batch
                    if any(f in (p.categories[0].lower() if p.categories else "") for f in filters)
                ]
            results.extend(batch)
        return results[: query.max_results]


register(BiorxivSource())
