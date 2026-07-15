"""Roadmap verification-checklist item: seed avoid_topics with "board
diversity, employee satisfaction", run a digest against a batch known to
contain a board-diversity paper, and confirm it is flagged/suppressed
correctly -- fully offline, no network or arXiv access involved."""

from __future__ import annotations

import tempfile
from pathlib import Path

from paperpulse.config import Config
from paperpulse.models import Paper
from paperpulse.pipeline import run_digest
from paperpulse.topics import TopicLog

_BATCH = [
    Paper(
        id="board1",
        title="Board Gender Diversity and Stock Returns",
        abstract="We study board gender diversity and its relation to firm "
        "performance and stock returns across a panel of listed firms.",
    ),
    Paper(
        id="momentum1",
        title="Cross-Sectional Momentum in International Equity Markets",
        abstract="We study price momentum strategies and their out-of-sample "
        "performance across multiple international equity markets and time "
        "periods, net of transaction costs.",
    ),
    Paper(
        id="novel1",
        title="Satellite-Derived Nighttime Luminosity as a Firm Growth Signal",
        abstract="We introduce a novel dataset of satellite-derived nighttime "
        "luminosity and link it to unlisted private firm revenue growth.",
    ),
]


def test_avoid_topics_and_known_topics_suppress_board_diversity_paper():
    with tempfile.TemporaryDirectory() as tmp:
        topics_db = Path(tmp) / "topics.db"
        log = TopicLog(topics_db)
        try:
            log.add(
                "board diversity",
                aliases=["board gender diversity"],
                source="manual",
                result="dead",
                notes="tried 6 variants over 2025, no edge",
            )
        finally:
            log.close()

        config = Config(
            embedding_backend="hashing",
            interests="equity factor research: momentum, quality, alternative data",
            avoid_topics=["board diversity", "employee satisfaction"],
            avoid_weight=1.0,
            topics_db=str(topics_db),
            state_path=str(Path(tmp) / "state.json"),
            top_n=3,
            min_score=-10.0,  # keep all 3 so we can inspect ranking, not just filtering
            trust=True,
            contradictions=False,
        )

        import paperpulse.pipeline as pipeline_mod

        original_fetch = pipeline_mod._fetch
        pipeline_mod._fetch = lambda cfg: _BATCH
        try:
            result = run_digest(config, dry_run=True)
        finally:
            pipeline_mod._fetch = original_fetch

        by_id = {item.paper.id: item for item in result.ranked}
        board_item = by_id["board1"]
        others = [by_id["momentum1"].score, by_id["novel1"].score]

        # Suppressed: avoid_topics should push it below both unrelated papers.
        assert board_item.score < min(others)

        # Flagged: the known_topic signal should catch the dead-logged match.
        assert board_item.trust is not None
        known_topic_signals = [s for s in board_item.trust.signals if s.name == "known_topic"]
        assert known_topic_signals and known_topic_signals[0].status != "ok"
        assert "board diversity" in known_topic_signals[0].note.lower()
