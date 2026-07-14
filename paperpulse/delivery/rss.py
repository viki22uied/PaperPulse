"""RSS 2.0 feed output.

Each ranked paper becomes an item, with its relevance score and trust badge in
the description so a feed reader shows the triage at a glance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from xml.sax.saxutils import escape

from ..models import RankedPaper


def _item(item: RankedPaper) -> str:
    paper = item.paper
    badge = getattr(item.trust, "badge", None)
    bits = [f"Relevance {item.score:.2f}"]
    if badge:
        bits.append(f"trust: {badge}")
    if item.summary:
        bits.append(item.summary)
    description = escape(" — ".join(bits))
    pub = (paper.published or datetime.now(timezone.utc)).strftime(
        "%a, %d %b %Y %H:%M:%S %z"
    ) or ""
    return (
        "    <item>\n"
        f"      <title>{escape(paper.title)}</title>\n"
        f"      <link>{escape(paper.url)}</link>\n"
        f"      <guid isPermaLink=\"false\">{escape(paper.id)}</guid>\n"
        f"      <pubDate>{pub}</pubDate>\n"
        f"      <description>{description}</description>\n"
        "    </item>"
    )


def render_rss(
    ranked: list[RankedPaper],
    *,
    title: str = "PaperPulse digest",
    link: str = "https://github.com/viki22uied/research-guide",
    description: str = "Relevance-ranked arXiv digest",
) -> str:
    items = "\n".join(_item(r) for r in ranked)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <link>{escape(link)}</link>\n"
        f"    <description>{escape(description)}</description>\n"
        f"{items}\n"
        "  </channel>\n"
        "</rss>\n"
    )
