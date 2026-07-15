"""Known/already-tried topic log: shared storage for A2 (known factor
families) and D2 (personal already-tried log)."""

import tempfile
from pathlib import Path

from paperpulse import trust
from paperpulse.config import Config
from paperpulse.models import Paper
from paperpulse.pipeline import apply_feedback
from paperpulse.store import State
from paperpulse.topics import TopicEntry, TopicLog, match_text


def _paper(title, abstract=""):
    return Paper(id="1", title=title, abstract=abstract)


def test_add_and_all_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        db = TopicLog(Path(tmp) / "t.db")
        try:
            db.add(
                "board diversity",
                aliases=["gender diversity board", "board composition"],
                source="manual",
                result="dead",
                notes="tried 6 variants, no edge",
            )
            entries = db.all()
        finally:
            db.close()
        assert len(entries) == 1
        assert entries[0].name == "board diversity"
        assert entries[0].result == "dead"
        assert "board composition" in entries[0].aliases


def test_match_text_hits_alias():
    entries = [
        TopicEntry(name="low_volatility", aliases=["betting against beta"], result="weak")
    ]
    match = match_text("A study of betting against beta anomalies in equities.", entries)
    assert match is not None
    assert match.name == "low_volatility"


def test_match_text_no_hit():
    entries = [TopicEntry(name="momentum", aliases=["price momentum"])]
    assert match_text("A paper about protein folding.", entries) is None


def test_known_topic_signal_flags_dead_as_flag():
    entries = [TopicEntry(name="board diversity", result="dead", source="manual")]
    paper = _paper("Board diversity and stock returns")
    ctx = trust.SignalContext(topics=entries)
    report = trust.assess(paper, enabled=["known_topic"], context=ctx)
    assert report.signals[0].status == trust.FLAG


def test_known_topic_signal_warns_on_known_family():
    entries = [
        TopicEntry(name="low_volatility", aliases=["betting against beta"], result="untested", source="literature")
    ]
    paper = _paper("Betting against beta in emerging markets")
    ctx = trust.SignalContext(topics=entries)
    report = trust.assess(paper, enabled=["known_topic"], context=ctx)
    assert report.signals[0].status == trust.WARN


def test_known_topic_signal_ok_when_unconfigured():
    paper = _paper("Some unrelated paper")
    report = trust.assess(paper, enabled=["known_topic"])
    assert report.signals[0].status == trust.OK


def test_feedback_reason_logs_to_topics_db():
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        topics_db = Path(tmp) / "topics.db"
        state = State(shown={"1": {"title": "Board diversity and returns", "abstract": "..."}})
        state.save(state_path)

        config = Config(
            state_path=str(state_path),
            topics_db=str(topics_db),
            embedding_backend="hashing",
        )
        apply_feedback(config, [], ["1"], reason="already-tried")

        log = TopicLog(topics_db)
        try:
            entries = log.all()
        finally:
            log.close()
        assert len(entries) == 1
        assert entries[0].result == "dead"
        assert entries[0].name == "Board diversity and returns"


def test_feedback_reason_irrelevant_does_not_log():
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        topics_db = Path(tmp) / "topics.db"
        state = State(shown={"1": {"title": "Some paper", "abstract": "..."}})
        state.save(state_path)

        config = Config(
            state_path=str(state_path),
            topics_db=str(topics_db),
            embedding_backend="hashing",
        )
        apply_feedback(config, [], ["1"], reason="irrelevant")

        assert not topics_db.exists()
