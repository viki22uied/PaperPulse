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


def _relevance_percentile(score: float, all_scores: list[float]) -> int:
    """Where this paper's raw cosine score sits within *today's* batch.

    Absolute cosine similarity against one averaged interest vector isn't
    built to produce a 0-1 scale where 1.0 is achievable -- in practice a
    whole batch can cluster between 0.00 and 0.30, which makes a fixed-scale
    bar misleading (a 0.30 looks "meaningfully better" than a 0.02 when the
    gap may just be embedding noise). A batch-relative percentile is the
    honest version of the same bar.
    """
    if len(all_scores) <= 1:
        return 100
    rank = sum(1 for s in all_scores if s <= score)
    return round(100 * rank / len(all_scores))


def _relevance_bar(percentile: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percentile / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def _trust_block(item: RankedPaper) -> list[str]:
    report = item.trust
    if report is None:
        return []
    badge = _BADGE_LABEL.get(getattr(report, "badge", ""), "")
    lines = [f"**Signal check:** {badge} (score {report.score:.2f})"]
    # Substantive flags only -- hygiene/metadata notes (preprint status, no
    # code link) are true of most preprints, carry almost no paper-specific
    # signal, and are rendered separately below so they can't visually compete
    # with the flags that actually vary paper-to-paper.
    flags = getattr(report, "flags", [])
    if flags:
        lines.append("")
        for sig in flags:
            tag = "FLAG" if sig.status == "flag" else "WARN"
            lines.append(f"- **{tag}** *{sig.name}* — {sig.note}")
    hygiene = getattr(report, "hygiene_notes", [])
    if hygiene:
        lines.append("")
        notes = "; ".join(f"{sig.name} — {sig.note}" for sig in hygiene)
        lines.append(f"*Metadata: {notes}*")
    lines.append("")
    return lines


_TESTABILITY_LABEL = {
    "strong": "🎯 strong",
    "partial": "🔎 partial",
    "vague": "🌫️ vague",
}


def _alpha_block(item: RankedPaper) -> list[str]:
    """The paper's testable claim, and what you'd still have to supply."""
    card = item.alpha
    if card is None:
        return []
    label = _TESTABILITY_LABEL.get(card.testability, card.testability)
    lines = [f"**Alpha card:** {label} (testability {card.testability_score}/4)", ""]
    if card.claim:
        lines.append(f"- *Claim* — {card.claim}")
    if card.effects:
        lines.append(f"- *Reported* — {', '.join(card.effects)}")
    if card.data_sources:
        lines.append(f"- *Data* — {', '.join(card.data_sources)}")
    if card.universe:
        lines.append(f"- *Universe* — {', '.join(card.universe)}")
    if card.period:
        lines.append(f"- *Period* — {card.period}")
    if card.missing:
        scope = "in the paper" if card.from_full_text else "in the abstract"
        lines.append(f"- *Not stated {scope}* — {', '.join(card.missing)}")
    lines.append("")
    return lines


_TIER_LABELS = ("Strongest matches", "Standard", "Lower relevance")


def _tier_for(percentile: int) -> int:
    if percentile >= 67:
        return 0
    if percentile >= 34:
        return 1
    return 2


def _scan_table(ranked: list[RankedPaper], percentiles: list[int]) -> list[str]:
    """Single-line-per-paper table up top, so a 50-paper batch can be triaged
    before reading any entry in depth."""
    lines = ["| # | Title | Relevance | Trust |", "|---|---|---|---|"]
    for i, (item, pct) in enumerate(zip(ranked, percentiles), start=1):
        title = item.paper.title
        if len(title) > 70:
            title = title[:67] + "..."
        badge = _BADGE_LABEL.get(item.trust.badge, "—") if item.trust else "—"
        lines.append(f"| {i} | {title} | {pct}th pct | {badge} |")
    lines.append("")
    return lines


def _entry_block(n: int, item: RankedPaper, percentile: int) -> list[str]:
    paper = item.paper
    lines = [
        f"### {n}. {paper.title}",
        "",
        f"`{_relevance_bar(percentile)}` relevance **{item.score:.2f}** "
        f"({percentile}th percentile today)  ·  "
        f"{_authors_line(paper.authors)}  ·  "
        f"{', '.join(paper.categories[:3])}",
        "",
    ]
    if item.why_rank:
        lines += [f"*{item.why_rank}*", ""]
    if item.summary:
        lines += [item.summary, ""]
    if item.regions:
        lines += [f"*Region: {', '.join(item.regions)}*", ""]
    if item.region_note:
        lines += [item.region_note, ""]
    lines += _alpha_block(item)
    lines += _trust_block(item)
    links = [f"[abstract]({paper.url})"]
    if paper.pdf_url:
        links.append(f"[pdf]({paper.pdf_url})")
    links.append(f"`{paper.id}`")
    lines += ["  ·  ".join(links), ""]
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
        lines += ["No papers cleared the relevance threshold today.", ""]
        return "\n".join(lines)

    lines += [f"**{len(ranked)} papers worth your time.**", ""]

    all_scores = [item.score for item in ranked]
    percentiles = [_relevance_percentile(item.score, all_scores) for item in ranked]

    lines += ["## Quick scan", ""]
    lines += _scan_table(ranked, percentiles)

    # Relevance-tiered grouping: the lowest-scoring survivors of the cut don't
    # get the same visual weight as the strongest matches, instead of one flat
    # numbered list running from the top score down to the cutoff.
    tiered: list[list[int]] = [[], [], []]
    for idx, pct in enumerate(percentiles):
        tiered[_tier_for(pct)].append(idx)

    n = 0
    for tier_idx, label in enumerate(_TIER_LABELS):
        idxs = tiered[tier_idx]
        if not idxs:
            continue
        lines += [f"## {label}", ""]
        for idx in idxs:
            n += 1
            lines += _entry_block(n, ranked[idx], percentiles[idx])

    lines += [
        "---",
        "",
        "*Mark papers useful with "
        "`paperpulse feedback --like <id> --dislike <id>` to sharpen future "
        "digests.*",
        "",
    ]
    return "\n".join(lines)
