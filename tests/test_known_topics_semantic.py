"""Opt-in semantic match for the known-topics log, plus the false-positive
validation the roadmap requires before a similarity-based signal ships (same
bar as tests/test_literature_novelty.py and test_weak_result_validation.py).

The deterministic name/alias match already covers exact and near-exact wording.
This path only exists for paraphrases it cannot see -- so the sample below is
deliberately built from wordings that share *meaning* but not the logged
phrase, and negatives that share *vocabulary* but not the topic.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from paperpulse import trust
from paperpulse.config import Config
from paperpulse.embeddings import HashingBackend
from paperpulse.models import Paper, RankedPaper
from paperpulse.pipeline import _attach_trust, _topic_text
from paperpulse.topics import TopicEntry, TopicLog, match_text

_DEAD_TOPIC = TopicEntry(
    name="board diversity",
    aliases=["board gender diversity"],
    source="manual",
    result="dead",
    notes="tried 6 variants over 2025, no edge",
)


def _backend():
    return HashingBackend(dim=4096)


def _seed(tmp: str) -> Path:
    db = Path(tmp) / "topics.db"
    log = TopicLog(db)
    try:
        log.add(
            _DEAD_TOPIC.name,
            aliases=_DEAD_TOPIC.aliases,
            source=_DEAD_TOPIC.source,
            result=_DEAD_TOPIC.result,
            notes=_DEAD_TOPIC.notes,
        )
    finally:
        log.close()
    return db


def _config(db: Path, *, semantic: bool, threshold: float | None = None) -> Config:
    """``threshold=None`` inherits Config's real default -- the validation below
    must measure the shipped value, not a number pinned in the test helper."""
    kwargs = {} if threshold is None else {"known_topics_semantic_threshold": threshold}
    return Config(
        embedding_backend="hashing",
        topics_db=str(db),
        trust=True,
        trust_signals=["known_topic"],
        known_topics_semantic=semantic,
        **kwargs,
    )


def _assess(config: Config, texts: list[str]) -> list[RankedPaper]:
    backend = _backend()
    ranked = [
        RankedPaper(paper=Paper(id=str(i), title="", abstract=t), score=0.5)
        for i, t in enumerate(texts)
    ]
    _attach_trust(config, ranked, backend=backend)
    return ranked


def _known_signal(item: RankedPaper):
    assert item.trust is not None
    return next(s for s in item.trust.signals if s.name == "known_topic")


def test_topic_text_excludes_notes():
    # Notes describe the outcome ("no edge"), not the topic; embedding them
    # would drag the vector away from what we match against.
    assert _topic_text(_DEAD_TOPIC) == "board diversity board gender diversity"


def test_semantic_match_is_off_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        db = _seed(tmp)
        paraphrase = (
            "We examine how the gender composition of corporate boards relates "
            "to shareholder value in listed firms."
        )
        # Guard the premise: this must NOT be caught by the exact matcher, or
        # the test proves nothing about the semantic path.
        assert match_text(paraphrase, [_DEAD_TOPIC]) is None

        off = _assess(_config(db, semantic=False), [paraphrase])[0]
        assert _known_signal(off).status == trust.OK


def test_exact_match_still_wins_and_is_labelled():
    with tempfile.TemporaryDirectory() as tmp:
        db = _seed(tmp)
        exact = "We study board gender diversity and stock returns."
        item = _assess(_config(db, semantic=True), [exact])[0]
        sig = _known_signal(item)
        assert sig.status == trust.FLAG
        assert "exact match" in sig.note
        # evidence must stay the bare topic name: _attach_regions and
        # `factors check` both look the entry back up by it.
        assert sig.evidence == "board diversity"


def test_semantic_match_is_labelled_and_less_confident():
    with tempfile.TemporaryDirectory() as tmp:
        db = _seed(tmp)
        # Threshold forced low to exercise the path deterministically; the
        # measured-rate test below uses the real default.
        paraphrase = (
            "We examine how the gender composition of corporate boards relates "
            "to shareholder value in listed firms."
        )
        item = _assess(_config(db, semantic=True, threshold=0.05), [paraphrase])[0]
        sig = _known_signal(item)
        assert sig.status == trust.FLAG
        assert "semantic match" in sig.note
        assert sig.evidence == "board diversity"  # still the bare name
        assert sig.confidence < 0.8  # discounted vs an exact match


# label: True => a paraphrase of the logged dead topic (should match),
# False => a different topic entirely (must NOT match).
_LABELED = [
    (True, "We examine how the gender composition of corporate boards relates "
           "to shareholder value in listed firms."),
    (True, "This paper studies female representation among corporate directors "
           "and its link to firm performance."),
    (True, "We test whether the share of women on the board of directors "
           "predicts subsequent equity returns."),
    (True, "Using a panel of listed companies, we relate the proportion of "
           "female directors to long-run stock performance."),
    (True, "We revisit whether diverse boards of directors deliver superior "
           "shareholder outcomes."),
    (False, "We introduce a novel dataset of satellite-derived nighttime "
            "luminosity and link it to unlisted private firm revenue growth."),
    (False, "We study how algorithmic trading affects limit order book "
            "microstructure using a proprietary exchange colocation dataset."),
    (False, "We propose a new NLP pipeline that extracts supply-chain "
            "relationships from earnings call transcripts."),
    (False, "We analyze how corporate patent citation networks predict future "
            "R&D spending using a graph-embedding approach."),
    (False, "We study the effect of extreme weather events on regional "
            "logistics delays using shipping AIS tracking data."),
    # Adversarial negatives: same corporate-governance vocabulary, different
    # topic. These are what a bag-of-words backend is most likely to trip on.
    (False, "We study how executive compensation structure affects corporate "
            "risk taking in listed firms."),
    (False, "We examine how board size and director independence relate to "
            "the cost of debt for listed firms."),
]


def _rates(ranked: list[RankedPaper]) -> tuple[float, float, list, list]:
    def matched(item: RankedPaper) -> bool:
        return _known_signal(item).status != trust.OK

    pos = [r for r, (lab, _) in zip(ranked, _LABELED) if lab]
    neg = [r for r, (lab, _) in zip(ranked, _LABELED) if not lab]
    tp = [r for r in pos if matched(r)]
    fp = [r for r in neg if matched(r)]
    return len(tp) / len(pos), len(fp) / len(neg), tp, fp


def test_semantic_match_is_inert_with_the_default_hashing_backend():
    """Documents a real limitation, so nobody enables this expecting it to work
    on the default backend.

    HashingBackend is a bag of word n-grams: "female representation among
    corporate directors" and a logged "board diversity" share *no* tokens, so
    the cosine is ~0 (measured 0.00-0.06 across the sample below) and nothing
    clears the 0.35 threshold. It fails safe -- inert, not misfiring -- but it
    is not doing anything. The semantic path needs sentence-transformers.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _seed(tmp)
        ranked = _assess(_config(db, semantic=True), [t for _, t in _LABELED])
        tp_rate, fp_rate, _, fp = _rates(ranked)
        print(f"known_topic semantic [hashing]: fp_rate={fp_rate:.2f}, tp_rate={tp_rate:.2f}")
        assert fp_rate == 0.0, [r.paper.abstract for r in fp]
        assert tp_rate == 0.0, "hashing unexpectedly matched a paraphrase -- re-measure the threshold"


def test_semantic_match_validated_with_sentence_transformers():
    """The validation that actually gates this feature (roadmap sub-requirement).

    Skipped where the optional `semantic` extra isn't installed -- including CI,
    which installs only [dev]. Documented result with
    sentence-transformers/all-MiniLM-L6-v2 over the 12 labeled abstracts below:
    tp_rate=1.00 (5/5), fp_rate=0.00 (0/7) at the default 0.35 threshold.

    Margin: highest negative 0.290 ("board size and director independence" --
    same governance vocabulary, different topic), lowest positive 0.402. The
    threshold sits between them by design rather than tuned to either edge.
    """
    import pytest

    pytest.importorskip("sentence_transformers")

    with tempfile.TemporaryDirectory() as tmp:
        db = _seed(tmp)
        from paperpulse.embeddings import SentenceTransformerBackend

        config = _config(db, semantic=True)
        ranked = [
            RankedPaper(paper=Paper(id=str(i), title="", abstract=t), score=0.5)
            for i, (_, t) in enumerate(_LABELED)
        ]
        _attach_trust(config, ranked, backend=SentenceTransformerBackend())
        tp_rate, fp_rate, tp, fp = _rates(ranked)
        print(
            f"known_topic semantic [sentence-transformers]: "
            f"fp_rate={fp_rate:.2f} ({len(fp)}/7), tp_rate={tp_rate:.2f} ({len(tp)}/5) "
            f"@ threshold={config.known_topics_semantic_threshold}"
        )
        # A false flag tells you to skip a paper you never actually tried --
        # the expensive error here, so it gets the tighter gate.
        assert fp_rate <= 0.20, [r.paper.abstract for r in fp]
        assert tp_rate >= 0.80, "semantic match stopped catching paraphrases"
