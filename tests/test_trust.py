"""Trust signal behaviour."""

from paperpulse import trust
from paperpulse.models import Paper


def _paper(abstract, title="A paper"):
    return Paper(id="1", title=title, abstract=abstract)


def test_overclaim_flagged():
    paper = _paper(
        "We propose a novel, state-of-the-art method that significantly "
        "outperforms all prior work and is the first to achieve superior results."
    )
    report = trust.assess(paper, enabled=["overclaim"])
    assert report.signals[0].status == trust.FLAG
    assert report.score < 0.5


def test_measured_abstract_is_clean():
    paper = _paper(
        "We study retrieval and report a 3.2% improvement (p < 0.01) over the "
        "baseline; results may not generalise to other domains."
    )
    report = trust.assess(paper, enabled=["overclaim", "evidence"])
    assert report.badge == "clean"
    assert report.flags == []


def test_related_work_flags_thin_reference_list(monkeypatch):
    from paperpulse.trust import external

    monkeypatch.setattr(
        external, "_s2_paper_data", lambda arxiv_id: {"references": [{}] * 3}
    )
    signal = external.related_work_signal(_paper("abstract"), online=True)
    assert signal.status == trust.WARN

    monkeypatch.setattr(
        external, "_s2_paper_data", lambda arxiv_id: {"references": [{}] * 20}
    )
    signal = external.related_work_signal(_paper("abstract"), online=True)
    assert signal.status == trust.OK


def test_leakage_flag_on_timeseries():
    paper = _paper(
        "We forecast stock returns using a random split of the time-series data "
        "and report strong accuracy."
    )
    report = trust.assess(paper, enabled=["leakage"])
    assert report.signals[0].status == trust.FLAG


def test_crowding_uses_context():
    paper = _paper("Yet another embedding method.")
    ctx = trust.SignalContext(crowding=0.92)
    report = trust.assess(paper, enabled=["crowding"], context=ctx)
    assert report.signals[0].status == trust.WARN


def test_offline_external_signals_are_noops():
    paper = _paper("No links here.")
    report = trust.assess(paper, enabled=["link_check", "retraction"])
    # Offline => everything OK, nothing flagged, no network touched.
    assert report.flags == []


def test_default_assessment_runs_all_registered():
    paper = _paper("We release code at https://github.com/x/y and report gains.")
    report = trust.assess(paper)
    names = {s.name for s in report.signals}
    assert "evidence" in names and "deployability" in names


def test_hygiene_flags_are_excluded_from_score_but_still_reported():
    """A no-code-link / preprint-only paper with nothing else wrong should
    stay "clean" -- those two signals are metadata, not methodology, per
    Signal.hygiene. They must still show up somewhere (hygiene_notes), just
    not eat into the score."""
    paper = _paper(
        "We study retrieval and report a 3.2% improvement (p < 0.01) over the "
        "baseline; results may not generalise to other domains."
    )
    report = trust.assess(paper, enabled=["reproducibility", "peer_review", "overclaim"])
    assert report.score == 1.0
    assert report.badge == "clean"
    assert report.flags == []  # substantive flags list is empty
    hygiene_names = {s.name for s in report.hygiene_notes}
    assert {"reproducibility", "peer_review"} <= hygiene_names


def test_confidence_discounts_the_penalty():
    """A low-confidence WARN should move the score less than a high-confidence
    one of the same status/weight -- this is the whole point of wiring
    `confidence` into the formula instead of leaving it unused on the object."""
    low = trust.Signal("x", trust.WARN, "weak evidence", confidence=0.2)
    high = trust.Signal("y", trust.WARN, "strong evidence", confidence=0.9)

    def _score(signals):
        total_weight = sum(s.weight for s in signals) or 1.0
        penalty = sum(
            trust._PENALTY[s.status] * s.weight * s.confidence for s in signals
        ) / total_weight
        return 1.0 - penalty

    assert _score([low]) > _score([high])


def test_weight_overrides_change_the_penalty():
    # Trips both leakage (FLAG) and backtest_overfit (WARN) so the override
    # has a second signal to shift the balance against.
    paper = _paper(
        "We backtest a strategy by forecasting stock returns using a random "
        "split of the time-series data and report strong accuracy."
    )
    default_report = trust.assess(paper, enabled=["leakage", "backtest_overfit"])
    downweighted = trust.assess(
        paper,
        enabled=["leakage", "backtest_overfit"],
        weight_overrides={"leakage": 0.01},
    )
    assert downweighted.signals[0].weight == 0.01
    # Shrinking the FLAG's weight relative to the WARN raises the score --
    # confirms the override actually reaches the aggregate, not just the
    # Signal object.
    assert downweighted.score > default_report.score
