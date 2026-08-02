"""Citation export -- BibTeX, for dropping a digest straight into Zotero,
Mendeley, or a LaTeX bibliography instead of copy-pasting titles by hand.
"""

from __future__ import annotations

import re

from .models import Paper, RankedPaper

# Modern arXiv id: "2401.01234" or "2401.01234v2". Old-style ids
# ("cs.LG/0501001") exist but are rare enough in a *current* digest (arXiv
# retired that scheme in 2007) that falling back to a generic entry for them
# is the right tradeoff over adding a second regex nobody will hit.
_ARXIV_ID = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "using", "based", "toward", "towards", "via", "under", "beyond",
}


def _cite_key(paper: Paper) -> str:
    """A short, deterministic, human-recognizable key: authorYEARword."""
    last = ""
    if paper.authors and paper.authors[0].split():
        last = paper.authors[0].split()[-1]
    last = re.sub(r"[^A-Za-z]", "", last).lower() or "anon"
    year = str(paper.published.year) if paper.published else "nd"
    word = ""
    for w in re.findall(r"[A-Za-z]{3,}", paper.title):
        low = w.lower()
        if low not in _STOPWORDS:
            word = low
            break
    return f"{last}{year}{word}"


def _escape(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}")


def to_bibtex(paper: Paper) -> str:
    """A single paper as a BibTeX entry. arXiv ids get the standard
    eprint/archivePrefix/primaryClass fields real reference managers expect;
    anything else (bioRxiv, PubMed, SSRN/OpenAlex) falls back to a generic
    ``@misc`` with a URL, since those don't have one universal BibTeX
    convention the way arXiv does."""
    key = _cite_key(paper)
    authors = " and ".join(paper.authors) if paper.authors else "Unknown"
    lines = [f"@misc{{{key},"]
    lines.append(f"  title = {{{_escape(paper.title)}}},")
    lines.append(f"  author = {{{_escape(authors)}}},")
    if paper.published:
        lines.append(f"  year = {{{paper.published.year}}},")

    m = _ARXIV_ID.match(paper.id)
    if m:
        lines.append(f"  eprint = {{{m.group(1)}}},")
        lines.append("  archivePrefix = {arXiv},")
        if paper.categories:
            lines.append(f"  primaryClass = {{{paper.categories[0]}}},")
    if paper.url:
        lines.append(f"  url = {{{paper.url}}},")
    lines.append("}")
    return "\n".join(lines)


def digest_to_bibtex(ranked: list[RankedPaper]) -> str:
    return "\n\n".join(to_bibtex(item.paper) for item in ranked) + "\n"


__all__ = ["to_bibtex", "digest_to_bibtex"]
