""""What changed since last week" diff -- fully offline, no network.

Follows tests/test_end_to_end_roadmap.py: a synthetic batch is swapped in for
`_fetch`, a real digest run records a snapshot, then a second batch is diffed
against it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import paperpulse.pipeline as pipeline_mod
from paperpulse.config import Config
from paperpulse.models import Paper
from paperpulse.pipeline import diff_digest, run_digest, snapshot_key
from paperpulse.store import MAX_SNAPSHOTS_PER_KEY, State
from paperpulse.topics import TopicLog

# A contradiction pair only forms when the two sides oppose, so a *flip* is
# both sides swapping: mom1 said "works" and mom2 said "doesn't"; after both are
# revised, mom1 says "doesn't" and mom2 says "works". (If only one side flipped
# they would agree, and the pair would dissolve rather than reverse.)
#
# The shared body keeps batch similarity above contradiction_map's 0.6 gate in
# both runs; the verdict sentence carries the polarity. Wording is deliberately
# one-sided -- `_polarity` counts positive minus negative matches, so a phrase
# like "fail to improve" nets to zero and forms no pair at all.
_SHARED_BODY = (
    "momentum strategies applied to international equity markets using a long "
    "short portfolio of past winners and losers, evaluated net of transaction "
    "costs. "
)
_VERDICT_POSITIVE = (
    "We find momentum strategies improve risk adjusted returns, outperform the "
    "benchmark, and deliver a superior effective gain."
)
_VERDICT_NEGATIVE = (
    "We find momentum strategies degrade risk adjusted returns, worse than the "
    "benchmark; the reported edge is an illusion that cannot persist."
)

_MOM1_POSITIVE = Paper(id="mom1", title="Momentum Evidence", abstract=_SHARED_BODY + _VERDICT_POSITIVE)
_MOM1_NEGATIVE = Paper(id="mom1", title="Momentum Evidence", abstract=_SHARED_BODY + _VERDICT_NEGATIVE)
_MOM2_NEGATIVE = Paper(id="mom2", title="Momentum Reassessed", abstract=_SHARED_BODY + _VERDICT_NEGATIVE)
_MOM2_POSITIVE = Paper(id="mom2", title="Momentum Reassessed", abstract=_SHARED_BODY + _VERDICT_POSITIVE)
_BOARD = Paper(
    id="board1",
    title="Board Gender Diversity and Stock Returns",
    abstract="We study board gender diversity and its relation to firm "
    "performance and stock returns across a panel of listed firms.",
)
_NEW_PAPER = Paper(
    id="new1",
    title="Satellite Luminosity as a Firm Growth Signal",
    abstract="We introduce a novel dataset of satellite-derived nighttime "
    "luminosity and link it to unlisted private firm revenue growth.",
)


def _config(tmp: str, topics_db: Path) -> Config:
    return Config(
        embedding_backend="hashing",
        interests="equity factor research: momentum, quality, alternative data",
        topics_db=str(topics_db),
        state_path=str(Path(tmp) / "state.json"),
        output_dir=str(Path(tmp) / "digests"),
        categories=["q-fin.TR"],
        top_n=10,
        min_score=-10.0,
        trust=True,
        contradictions=True,
    )


def _run_with(batch, fn, *args, **kwargs):
    original = pipeline_mod._fetch
    pipeline_mod._fetch = lambda cfg: batch
    try:
        return fn(*args, **kwargs)
    finally:
        pipeline_mod._fetch = original


def _seed_topics(topics_db: Path) -> None:
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


def test_diff_reports_new_papers_factor_evidence_and_polarity_flips():
    with tempfile.TemporaryDirectory() as tmp:
        topics_db = Path(tmp) / "topics.db"
        _seed_topics(topics_db)
        config = _config(tmp, topics_db)

        # Run 1 (recorded): mom1 says momentum works, mom2 says it doesn't.
        batch1 = [_MOM1_POSITIVE, _MOM2_NEGATIVE, _BOARD]
        _run_with(batch1, run_digest, config, dry_run=False)

        snap = State.load(config.state_path).latest_snapshot(snapshot_key(config))
        assert snap is not None, "a non-dry run must record a snapshot"
        assert set(snap["papers"]) == {"mom1", "mom2", "board1"}
        assert snap["contradictions"]["mom1|mom2"]["polarity_a"] == 1

        # Run 2: both sides are revised and swap, and a new paper appears.
        batch2 = [_MOM1_NEGATIVE, _MOM2_POSITIVE, _BOARD, _NEW_PAPER]
        diff = _run_with(batch2, diff_digest, config)

        assert not diff.is_first_run
        assert diff.since == snap["ts"]

        # 1. New papers: only new1. board1/mom1/mom2 were all in the snapshot,
        #    and must not resurface just because they were already "seen".
        assert [i.paper.id for i in diff.new_papers] == ["new1"]

        # 2. Fresh evidence on a tracked dead factor.
        names = [entry.name for entry, _ in diff.factor_evidence]
        assert "board diversity" in names
        matched_paper = next(i.paper.id for e, i in diff.factor_evidence if e.name == "board diversity")
        assert matched_paper == "board1"

        # 3. The mom1/mom2 disagreement reversed direction.
        flipped = {(a.id, b.id) for a, b, _ in diff.polarity_flips}
        assert ("mom1", "mom2") in flipped


def test_diff_without_baseline_reports_first_run():
    with tempfile.TemporaryDirectory() as tmp:
        topics_db = Path(tmp) / "topics.db"
        _seed_topics(topics_db)
        config = _config(tmp, topics_db)

        diff = _run_with([_MOM1_POSITIVE, _BOARD], diff_digest, config)
        assert diff.is_first_run
        assert diff.new_papers == []  # no baseline => don't call everything new


def test_diff_is_read_only_by_default():
    """GET /api/diff must be safe to repeat: the default must not write
    last_seen_at back, or the second call would report nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        topics_db = Path(tmp) / "topics.db"
        _seed_topics(topics_db)
        config = _config(tmp, topics_db)

        _run_with([_BOARD], run_digest, config, dry_run=False)

        first = _run_with([_BOARD, _NEW_PAPER], diff_digest, config)
        second = _run_with([_BOARD, _NEW_PAPER], diff_digest, config)
        assert [e.name for e, _ in first.factor_evidence] == ["board diversity"]
        assert [e.name for e, _ in second.factor_evidence] == ["board diversity"]

        # ...and mark=True does consume it.
        _run_with([_BOARD, _NEW_PAPER], diff_digest, config, mark=True)
        after = _run_with([_BOARD, _NEW_PAPER], diff_digest, config)
        assert after.factor_evidence == []


def test_snapshots_are_capped_per_category_set():
    state = State()
    for i in range(MAX_SNAPSHOTS_PER_KEY + 5):
        state.add_snapshot("q-fin.TR", {"ts": str(i), "papers": {}, "contradictions": {}})
    history = state.snapshots["q-fin.TR"]
    assert len(history) == MAX_SNAPSHOTS_PER_KEY
    assert history[-1]["ts"] == str(MAX_SNAPSHOTS_PER_KEY + 4)  # newest kept


def test_snapshots_are_keyed_per_category_set():
    with tempfile.TemporaryDirectory() as tmp:
        topics_db = Path(tmp) / "topics.db"
        _seed_topics(topics_db)
        config = _config(tmp, topics_db)
        _run_with([_MOM1_POSITIVE], run_digest, config, dry_run=False)

        # A different category set must not diff against q-fin.TR's snapshot.
        from dataclasses import replace

        other = replace(config, categories=["cs.LG"])
        diff = _run_with([_MOM1_POSITIVE], diff_digest, other)
        assert diff.is_first_run
