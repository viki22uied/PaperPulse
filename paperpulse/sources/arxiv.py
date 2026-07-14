"""Thin client over the public arXiv Atom API.

No auth required. We deliberately keep this dependency-free (urllib + the
stdlib XML parser) so ingestion works anywhere Python does.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from ..models import Paper
from .base import Query, register

API_URL = "https://export.arxiv.org/api/query"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    # arXiv timestamps look like 2024-01-31T09:30:00Z
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _entry_to_paper(entry: ET.Element) -> Paper:
    def text(tag: str) -> str:
        node = entry.find(f"atom:{tag}", _NS)
        return (node.text or "").strip() if node is not None else ""

    raw_id = text("id")  # e.g. http://arxiv.org/abs/2401.01234v1
    short_id = raw_id.rsplit("/", 1)[-1] if raw_id else ""

    authors = [
        (a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
        for a in entry.findall("atom:author", _NS)
    ]
    authors = [a for a in authors if a]

    categories = [
        c.attrib.get("term", "")
        for c in entry.findall("atom:category", _NS)
        if c.attrib.get("term")
    ]

    pdf_url = ""
    page_url = raw_id
    for link in entry.findall("atom:link", _NS):
        if link.attrib.get("title") == "pdf":
            pdf_url = link.attrib.get("href", "")
        elif link.attrib.get("rel") == "alternate":
            page_url = link.attrib.get("href", page_url)

    def arxiv_text(tag: str) -> str:
        node = entry.find(f"arxiv:{tag}", _NS)
        return " ".join((node.text or "").split()) if node is not None else ""

    return Paper(
        id=short_id,
        title=" ".join(text("title").split()),
        abstract=" ".join(text("summary").split()),
        authors=authors,
        categories=categories,
        published=_parse_date(text("published")),
        updated=_parse_date(text("updated")),
        url=page_url,
        pdf_url=pdf_url,
        comment=arxiv_text("comment"),
        journal_ref=arxiv_text("journal_ref"),
    )


def _fetch_page(query: str, start: int, page_size: int, timeout: float) -> list[Paper]:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": start,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "PaperPulse/0.1 (+https://github.com/)"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                root = ET.fromstring(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 1:
                raise
            time.sleep(3)  # back off: arXiv is rate-limiting us
    return [_entry_to_paper(e) for e in root.findall("atom:entry", _NS)]


def fetch_recent(
    categories: list[str],
    *,
    max_results: int = 200,
    page_size: int = 100,
    extra_query: str = "",
    timeout: float = 10.0,
    pause: float = 3.0,
) -> list[Paper]:
    """Fetch the most recent papers across one or more arXiv categories.

    ``categories`` are arXiv classifications such as ``cs.LG`` or ``q-fin.*``.
    The API is paginated; we page politely (arXiv asks for a few seconds
    between calls) until we have ``max_results`` entries.
    """
    if not categories:
        raise ValueError("at least one arXiv category is required")

    cat_query = " OR ".join(f"cat:{c}" for c in categories)
    query = f"({cat_query})"
    if extra_query:
        query = f"{query} AND ({extra_query})"

    papers: list[Paper] = []
    seen: set[str] = set()
    start = 0
    while len(papers) < max_results:
        want = min(page_size, max_results - len(papers))
        page = _fetch_page(query, start, want, timeout)
        if not page:
            break
        for paper in page:
            if paper.id and paper.id not in seen:
                seen.add(paper.id)
                papers.append(paper)
        start += want
        if len(page) < want:
            break  # reached the end of the result set
        time.sleep(pause)

    return papers[:max_results]


class ArxivSource:
    """:class:`~paperpulse.sources.base.Source` adapter for arXiv."""

    name = "arxiv"

    def fetch(self, query: Query) -> list[Paper]:
        extra = ""
        clauses = []
        if query.keywords:
            clauses.append(" OR ".join(f'all:"{k}"' for k in query.keywords))
        if query.authors:
            clauses.append(" OR ".join(f'au:"{a}"' for a in query.authors))
        if clauses:
            extra = " AND ".join(f"({c})" for c in clauses)
        categories = query.categories or ["cs.LG"]
        return fetch_recent(
            categories, max_results=query.max_results, extra_query=extra
        )


register(ArxivSource())
