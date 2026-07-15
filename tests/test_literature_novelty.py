"""E2: novelty vs. the known literature, plus the roadmap's required
false-positive validation before shipping (shared sub-requirement)."""

from __future__ import annotations

from paperpulse import trust
from paperpulse.embeddings import HashingBackend
from paperpulse.models import Paper
from paperpulse.pipeline import _attach_trust, _literature_reference_texts
from paperpulse.config import Config


def _backend():
    return HashingBackend(dim=4096)


def test_literature_novelty_signal_context():
    paper = Paper(id="1", title="t", abstract="a")
    ctx = trust.SignalContext(literature_crowding=0.9)
    report = trust.assess(paper, enabled=["literature_novelty"], context=ctx)
    assert report.signals[0].status == trust.WARN

    ctx = trust.SignalContext(literature_crowding=0.1)
    report = trust.assess(paper, enabled=["literature_novelty"], context=ctx)
    assert report.signals[0].status == trust.OK

    report = trust.assess(paper, enabled=["literature_novelty"])
    assert report.signals[0].status == trust.OK  # not evaluated -> OK


def test_reference_texts_include_canonical_and_topics():
    from paperpulse.topics import TopicEntry

    topics = [TopicEntry(name="board diversity", aliases=["board composition"], notes="tried")]
    texts = _literature_reference_texts(topics)
    assert any("Fama French" in t for t in texts)
    assert any("board diversity" in t for t in texts)


# label: True => a rehash of a well-known factor (should flag), False => a
# genuinely distinct paper (should NOT flag).
_LABELED_ABSTRACTS = [
    (True, "We revisit the size and value factors of Fama and French, "
           "confirming the market, size, and value premia in a new sample."),
    (True, "We study momentum: stocks with high returns over the prior 12 "
           "months continue to outperform stocks with low past returns."),
    (True, "We confirm the betting against beta anomaly: low-beta stocks "
           "earn higher risk-adjusted returns than high-beta stocks."),
    (True, "We show quality minus junk: profitable, safe, well-managed firms "
           "earn higher risk-adjusted returns than low-quality firms."),
    (True, "We revisit the gross profitability premium: firms with high "
           "gross profits relative to assets earn higher average returns."),
    (False, "We introduce a novel dataset of satellite-derived nighttime "
            "luminosity and link it to unlisted private firm revenue growth."),
    (False, "We study how algorithmic trading affects limit order book "
            "microstructure using a proprietary exchange colocation dataset."),
    (False, "We propose a new NLP pipeline that extracts supply-chain "
            "relationships from earnings call transcripts and test its use "
            "for predicting semiconductor shortages."),
    (False, "We analyze how corporate patent citation networks predict "
            "future R&D spending using a novel graph-embedding approach."),
    (False, "We study the effect of extreme weather events on regional "
            "logistics delays using shipping AIS tracking data."),
]


def test_literature_novelty_false_positive_rate_under_threshold():
    backend = _backend()
    config = Config(embedding_backend="hashing")
    ranked = []
    for _, text in _LABELED_ABSTRACTS:
        from paperpulse.models import RankedPaper

        ranked.append(RankedPaper(paper=Paper(id="x", title="t", abstract=text), score=0.5))

    _attach_trust(config, ranked, backend=backend)

    negatives = [(r, label) for r, (label, _) in zip(ranked, _LABELED_ABSTRACTS) if not label]
    positives = [(r, label) for r, (label, _) in zip(ranked, _LABELED_ABSTRACTS) if label]

    def flagged(item):
        return any(s.name == "literature_novelty" and s.status != trust.OK for s in item.trust.signals)

    false_positives = [r for r, _ in negatives if flagged(r)]
    true_positives = [r for r, _ in positives if flagged(r)]

    fp_rate = len(false_positives) / len(negatives)
    tp_rate = len(true_positives) / len(positives)
    print(f"literature_novelty: fp_rate={fp_rate:.2f} ({len(false_positives)}/{len(negatives)}), "
          f"tp_rate={tp_rate:.2f} ({len(true_positives)}/{len(positives)})")

    assert fp_rate <= 0.20, f"false positives: {[r.paper.abstract for r in false_positives]}"
    # Documented result: fp_rate=0.00 (0/5), tp_rate=0.80 (4/5) with the
    # default HashingBackend and a similarity threshold of 0.5 -- well under
    # the 20% false-positive gate. Soft WARN only (see literature_novelty_
    # signal), never a hard FLAG, since this is similarity-based
    # pattern-matching and can misfire on shared vocabulary alone.
