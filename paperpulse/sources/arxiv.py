"""Thin client over the public arXiv Atom API.

No auth required. We deliberately keep this dependency-free (urllib + the
stdlib XML parser) so ingestion works anywhere Python does.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from .. import __version__
from ..models import Paper
from .base import Query, register

API_URL = "https://export.arxiv.org/api/query"
# Daily announcement feed. A separate service from the search API above, so it
# stays up when the API blocks shared CI IPs (the 429/406 failures of the
# scheduled digest). Used only as a fallback: it has no search or paging.
LISTING_URL = "https://rss.arxiv.org/atom/"
USER_AGENT = f"PaperPulse/{__version__} (+https://github.com/viki22uied/PaperPulse)"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
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
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
    )
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                root = ET.fromstring(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == max_attempts - 1:
                raise
            wait = _retry_after_seconds(exc) or (3 * 2**attempt)  # 3, 6, 12, 24s
            time.sleep(wait)
        except (TimeoutError, urllib.error.URLError):
            # arXiv sometimes stalls a request instead of refusing it -- a read
            # timeout surfaces as a bare TimeoutError (not an HTTPError) and was
            # taking down the whole scheduled digest.
            if attempt == max_attempts - 1:
                raise
            time.sleep(3 * 2**attempt)
    return [_entry_to_paper(e) for e in root.findall("atom:entry", _NS)]


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    value = exc.headers.get("Retry-After") if exc.headers else None
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


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


_LISTING_PREFIX = re.compile(
    r"^arXiv:\S+\s+Announce Type:\s*\S+\s*(Abstract:\s*)?", re.IGNORECASE
)


def _parse_listing_date(text: str | None) -> datetime | None:
    # The listing feed uses offsets, e.g. 2024-02-05T00:00:00-05:00
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _listing_entry_to_paper(entry: ET.Element) -> Paper | None:
    """Map one listing-feed entry to a Paper; None for replacements."""
    announce = (
        entry.findtext("arxiv:announce_type", default="", namespaces=_NS) or ""
    ).strip()
    if announce.startswith("replace"):
        return None  # a new version of an old paper, not a new paper

    raw_id = (entry.findtext("atom:id", default="", namespaces=_NS) or "").strip()
    short_id = raw_id.split("oai:arXiv.org:", 1)[-1]
    if not short_id:
        return None

    creators = entry.findtext("dc:creator", default="", namespaces=_NS) or ""
    authors = [a.strip() for a in creators.split(",") if a.strip()]
    if not authors:
        authors = [
            (a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
            for a in entry.findall("atom:author", _NS)
        ]
        authors = [a for a in authors if a]

    page_url = f"https://arxiv.org/abs/{short_id}"
    for link in entry.findall("atom:link", _NS):
        if link.attrib.get("rel", "alternate") == "alternate" and link.attrib.get("href"):
            page_url = link.attrib["href"]

    summary = " ".join(
        (entry.findtext("atom:summary", default="", namespaces=_NS) or "").split()
    )
    published = _parse_listing_date(
        entry.findtext("atom:published", default="", namespaces=_NS)
    )
    return Paper(
        id=short_id,
        title=" ".join(
            (entry.findtext("atom:title", default="", namespaces=_NS) or "").split()
        ),
        abstract=_LISTING_PREFIX.sub("", summary),
        authors=authors,
        categories=[
            c.attrib["term"]
            for c in entry.findall("atom:category", _NS)
            if c.attrib.get("term")
        ],
        published=published,
        updated=_parse_listing_date(
            entry.findtext("atom:updated", default="", namespaces=_NS)
        ) or published,
        url=page_url,
        pdf_url=f"https://arxiv.org/pdf/{short_id}",
    )


def fetch_listing(categories: list[str], *, timeout: float = 30.0) -> list[Paper]:
    """Today's announced papers in ``categories`` from the listing feed.

    Retries timeouts and 429/503 like :func:`_fetch_page`. Wildcards such as
    ``q-fin.*`` map to the whole archive (``q-fin``).
    """
    feed = "+".join(c[:-2] if c.endswith(".*") else c for c in categories)
    request = urllib.request.Request(
        LISTING_URL + urllib.parse.quote(feed, safe="+.-"),
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"},
    )
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                root = ET.fromstring(response.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == max_attempts - 1:
                raise
            time.sleep(_retry_after_seconds(exc) or (3 * 2**attempt))
        except (TimeoutError, urllib.error.URLError):
            if attempt == max_attempts - 1:
                raise
            time.sleep(3 * 2**attempt)
    papers: list[Paper] = []
    seen: set[str] = set()
    for entry in root.findall("atom:entry", _NS):
        paper = _listing_entry_to_paper(entry)
        if paper is not None and paper.id not in seen:
            seen.add(paper.id)
            papers.append(paper)
    return papers


def _matches(paper: Paper, keywords: list[str], authors: list[str]) -> bool:
    """Local version of the API's ``all:"kw"`` / ``au:"name"`` filters."""
    if keywords:
        text = f"{paper.title} {paper.abstract}".lower()
        if not any(k.lower() in text for k in keywords):
            return False
    if authors:
        names = " | ".join(paper.authors).lower()
        if not any(a.lower() in names for a in authors):
            return False
    return True


# Failures that mean "the search API would not serve us right now" rather than
# a bug in our request: rate limits, blocks (403/406), outages, bad payloads.
_API_FAILURES = (urllib.error.URLError, TimeoutError, ET.ParseError)


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
        try:
            return fetch_recent(
                categories, max_results=query.max_results, extra_query=extra
            )
        except _API_FAILURES as api_exc:
            print(
                f"arXiv search API failed ({_describe(api_exc)}); "
                "falling back to the daily listing feed.",
                file=sys.stderr,
            )
            try:
                listing = fetch_listing(categories)
            except _API_FAILURES:
                raise api_exc from None  # report the original failure
        return [
            p for p in listing if _matches(p, query.keywords, query.authors)
        ][: query.max_results]


def _describe(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return type(exc).__name__


register(ArxivSource())
