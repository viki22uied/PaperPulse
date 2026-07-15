"""Known-factor-family / already-tried check.

Backed by ``paperpulse.topics`` -- a single shared log covering both the
maintained "known factor family" list (``source=literature``) and a personal
"I already tried this" record (``source=manual``). Fully offline: the entries
are loaded once per digest run and matched deterministically, no embeddings or
network calls needed.
"""

from __future__ import annotations

from ..models import Paper
from ..topics import TopicEntry, match_text
from . import FLAG, OK, WARN, Signal, signal


@signal("known_topic")
def known_topic_signal(
    paper: Paper, *, topics: list[TopicEntry] | None = None, **_
) -> Signal:
    if not topics:
        return Signal("known_topic", OK, "No known-topics log configured.")
    haystack = f"{paper.title} {paper.abstract}"
    match = match_text(haystack, topics)
    if match is None:
        return Signal("known_topic", OK, "No match in the known-topics log.")
    label = f"{match.name} ({match.source}, {match.result})"
    if match.result in ("dead", "weak"):
        note = f"Already logged as {match.result}: {label}."
        if match.notes:
            note += f" Notes: {match.notes}"
        return Signal("known_topic", FLAG, note, evidence=match.name, confidence=0.8)
    return Signal(
        "known_topic",
        WARN,
        f"Known factor family -- check for crowding before building: {label}.",
        evidence=match.name,
        confidence=0.6,
    )


__all__ = ["known_topic_signal"]
