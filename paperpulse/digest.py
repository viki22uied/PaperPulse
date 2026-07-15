"""Render a ranked list of papers as a Markdown digest."""

from __future__ import annotations

from datetime import date

from .models import RankedPaper

_BADGE_LABEL = {
    "clean": "🟢 clean",
    "mixed": "🟡 mixed",
    "caution": "🔴 caution",
}


def _authors_line(authors: list[str], limit: int = 4) -> str:
    if not authors:
        return "Unknown authors"
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f", +{len(authors) - limit} more"


def _relevance_bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, round(score * width)))
    return "█" * filled + "░" * (width - filled)


def _trust_block(item: RankedPaper) -> list[str]:
    report = item.trust
    if report is None:
        return []
    badge = _BADGE_LABEL.get(getattr(report, "badge", ""), "")
    lines = [f"**Signal check:** {badge} (score {report.score:.2f})"]
    flags = getattr(report, "flags", [])
    if flags:
        lines.append("")
        for sig in flags:
            marker = "⚠️" if sig.status == "warn" else "🚩"
            lines.append(f"- {marker} *{sig.name}* — {sig.note}")
    lines.append("")
    return lines


def render_markdown(
    ranked: list[RankedPaper],
    *,
    title: str = "PaperPulse Digest",
    subtitle: str = "",
    on_date: date | None = None,
) -> str:
    on_date = on_date or date.today()
    lines = [
        f"# {title}",
        "",
        f"*{on_date.isoformat()}*" + (f" — {subtitle}" if subtitle else ""),
        "",
    ]

    if not ranked:
        lines += ["No papers cleared the relevance threshold today. 🎉", ""]
        return "\n".join(lines)

    lines += [f"**{len(ranked)} papers worth your time.**", ""]

    for i, item in enumerate(ranked, start=1):
        paper = item.paper
        lines += [
            f"## {i}. {paper.title}",
            "",
            f"`{_relevance_bar(item.score)}` relevance **{item.score:.2f}**  ·  "
            f"{_authors_line(paper.authors)}  ·  "
            f"{', '.join(paper.categories[:3])}",
            "",
        ]
        if item.summary:
            lines += [item.summary, ""]
        if item.regions:
            lines += [f"*Region: {', '.join(item.regions)}*", ""]
        if item.region_note:
            lines += [f"✅ {item.region_note}", ""]
        lines += _trust_block(item)
        links = [f"[abstract]({paper.url})"]
        if paper.pdf_url:
            links.append(f"[pdf]({paper.pdf_url})")
        links.append(f"`{paper.id}`")
        lines += ["  ·  ".join(links), ""]

    lines += [
        "---",
        "",
        "*Mark papers useful with "
        "`paperpulse feedback --like <id> --dislike <id>` to sharpen future "
        "digests.*",
        "",
    ]
    return "\n".join(lines)
