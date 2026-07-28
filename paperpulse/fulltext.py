"""Best-effort full-text PDF fetch, for signals that look past the abstract
(reproducibility links, dead-link checks, alpha cards). Optional dependency
(``pip install paperpulse[pdf]``); fails soft to ``None`` if it's missing, the
download fails, or the PDF can't be parsed -- callers already treat
``full_text=None`` as "abstract only".

Also splits a paper into its own work versus its account of everyone else's.
That distinction matters: the first "Sharpe ratio of 0.8" in a paper is very
often in the literature review, describing a *different* paper. Anything that
attributes numbers to the paper in hand must read :func:`own_work_text`, not the
raw text."""

from __future__ import annotations

import io
import re
import urllib.request

from .models import Paper


# pdf_url comes from feed XML (semi-trusted); only follow it to hosts the
# supported sources actually serve PDFs from, and only over https.
_ALLOWED_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "nih.gov", "ssrn.com")


def _url_allowed(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS
    )


def fetch_full_text(paper: Paper, *, timeout: float = 20.0, max_bytes: int = 20_000_000) -> str | None:
    if not paper.pdf_url:
        return None
    # Some feeds still hand out http:// links; upgrade rather than reject.
    url = paper.pdf_url.replace("http://", "https://", 1)
    if not _url_allowed(url):
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "PaperPulse/0.1"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes)
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None


# Sections that describe *other people's* results. Numbers quoted here belong to
# the papers being surveyed, not to this one.
_OTHERS_WORK = re.compile(
    r"^\s*(?:\d+\.?\d*\s*|[IVX]+\.?\s*)?"
    r"(related\s+works?|literature\s+review|prior\s+works?|background|"
    r"references|bibliography|works?\s+cited)\s*$",
    re.I | re.M,
)
# Any heading at all, used to find where the excluded section ends.
_HEADING = re.compile(
    r"^\s*(?:\d+\.?\d*\s*|[IVX]+\.?\s*)?[A-Z][A-Za-z \-]{2,40}\s*$", re.M
)


def own_work_text(text: str) -> str:
    """``text`` with related-work / literature-review / reference sections cut.

    A section runs from its heading to the next heading. Headings in PDFs are
    unreliable, so this is deliberately conservative: if the boundary can't be
    found the section is left in rather than guessing and deleting real
    results."""
    if not text:
        return text
    spans: list[tuple[int, int]] = []
    for match in _OTHERS_WORK.finditer(text):
        next_heading = _HEADING.search(text, match.end())
        spans.append((match.start(), next_heading.start() if next_heading else len(text)))
    if not spans:
        return text
    kept: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        if start > cursor:
            kept.append(text[cursor:start])
        cursor = max(cursor, end)
    kept.append(text[cursor:])
    return "".join(kept)


__all__ = ["fetch_full_text", "own_work_text"]
