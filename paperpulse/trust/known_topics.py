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
    paper: Paper,
    *,
    topics: list[TopicEntry] | None = None,
    semantic_topic: TopicEntry | None = None,
    semantic_topic_similarity: float | None = None,
    **_,
) -> Signal:
    if not topics:
        return Signal("known_topic", OK, "No known-topics log configured.")
    haystack = f"{paper.title} {paper.abstract}"

    # The deterministic name/alias match always wins: it's exact, explainable,
    # and can't be wrong about *what* matched. The embedding match is only a
    # fallback for paraphrases it can't see, and is opt-in per config.
    match = match_text(haystack, topics)
    via = "exact match"
    confident = 1.0
    if match is None and semantic_topic is not None:
        match = semantic_topic
        sim = semantic_topic_similarity
        via = f"semantic match, cosine {sim:.2f}" if sim is not None else "semantic match"
        # A paraphrase match is a guess about meaning, not a substring fact, so
        # every verdict below carries less weight when it arrives this way.
        confident = 0.7
    if match is None:
        return Signal("known_topic", OK, "No match in the known-topics log.")

    label = f"{match.name} ({match.source}, {match.result}; {via})"
    # NOTE: `evidence` stays the bare topic name -- pipeline._attach_regions and
    # `factors check` both look the entry back up by it. The match kind belongs
    # in the note, not here.
    if match.result in ("dead", "weak"):
        note = f"Already logged as {match.result}: {label}."
        if match.notes:
            note += f" Notes: {match.notes}"
        return Signal(
            "known_topic", FLAG, note, evidence=match.name, confidence=0.8 * confident
        )
    if match.result == "promising":
        # A topic YOU logged as promising is a positive prior finding, not a
        # caution -- treating it the same as "untested" would misrepresent
        # your own research as a reason to be careful.
        note = f"Matches a topic previously logged as promising: {label}."
        if match.notes:
            note += f" Notes: {match.notes}"
        return Signal(
            "known_topic", OK, note, evidence=match.name, confidence=0.6 * confident
        )
    return Signal(
        "known_topic",
        WARN,
        f"Known factor family -- check for crowding before building: {label}.",
        evidence=match.name,
        confidence=0.6 * confident,
    )


__all__ = ["known_topic_signal"]
