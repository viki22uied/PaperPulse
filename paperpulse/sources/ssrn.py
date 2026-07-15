"""SSRN source -- via OpenAlex, not a direct SSRN scraper.

**Spike result (C2):** SSRN has no official public API, and third-party tools
that scrape SSRN directly exist but sit in ToS/robots.txt grey area we don't
want to inherit. OpenAlex (https://openalex.org) indexes SSRN as a first-class
source ("SSRN Electronic Journal", ~1.6M works) through its own free, keyless,
official REST API -- so this adapter never touches ssrn.com. That's the
"legitimate secondary aggregator with an open API" fallback the roadmap asked
for; no direct-scraper path was needed.

No API key required. OpenAlex asks (not requires) a contact email via
``?mailto=`` for their "polite pool" of faster/more reliable rate limits --
set ``OPENALEX_MAILTO`` to use it; otherwise requests still work, just
potentially slower under load. Docs: https://docs.openalex.org
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..models import Paper
from .base import Query, register

OPENALEX_WORKS = "https://api.openalex.org/works"
SSRN_SOURCE_ID = "S4210172589"  # OpenAlex id for "SSRN Electronic Journal"


def _get(params: dict, timeout: float) -> dict:
    mailto = os.getenv("OPENALEX_MAILTO")
    if mailto:
        params = {**params, "mailto": mailto}
    url = f"{OPENALEX_WORKS}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "PaperPulse/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as a word -> [positions] inverted index
    (a licensing workaround), not plain text -- rebuild the sentence."""
    if not inverted_index:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            slots[pos] = word
    return " ".join(slots[i] for i in sorted(slots))


def _work_to_paper(work: dict) -> Paper | None:
    openalex_id = work.get("id", "")
    wid = openalex_id.rsplit("/", 1)[-1] if openalex_id else ""
    if not wid:
        return None
    title = work.get("display_name") or work.get("title") or ""
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    topics = [t.get("display_name", "") for t in work.get("topics", []) if t.get("display_name")]

    published = None
    date_str = work.get("publication_date")
    if date_str:
        try:
            published = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    landing_url = (work.get("primary_location") or {}).get("landing_page_url") or openalex_id

    return Paper(
        id=f"openalex:{wid}",
        title=" ".join(title.split()),
        abstract=" ".join(abstract.split()),
        authors=authors,
        categories=topics[:3] or ["ssrn"],
        published=published,
        url=landing_url,
    )


class SSRNSource:
    """Recent SSRN working papers, sourced through OpenAlex."""

    name = "ssrn"

    def fetch(self, query: Query) -> list[Paper]:
        filters = [f"primary_location.source.id:{SSRN_SOURCE_ID}"]
        terms = list(query.keywords) or list(query.categories)
        search = " OR ".join(terms) if terms else None

        params = {
            "filter": ",".join(filters),
            "sort": "publication_date:desc",
            "per_page": min(query.max_results, 200),
        }
        if search:
            params["search"] = search

        data = _get(params, timeout=30.0)
        papers = [_work_to_paper(w) for w in data.get("results", [])]
        return [p for p in papers if p is not None][: query.max_results]


register(SSRNSource())
