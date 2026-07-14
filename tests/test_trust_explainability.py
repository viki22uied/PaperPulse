"""Peer-review signal, per-flag evidence, and confidence."""

from datetime import datetime, timezone

from paperpulse import trust
from paperpulse.models import Paper


def test_peer_review_published_vs_preprint():
    published = Paper(id="1", title="t", abstract="a", journal_ref="J. Finance 2023")
    assert trust.assess(published, enabled=["peer_review"]).signals[0].status == trust.OK

    accepted = Paper(id="1v1", title="t", abstract="a", comment="Accepted at ICML 2024")
    assert trust.assess(accepted, enabled=["peer_review"]).signals[0].status == trust.OK

    preprint = Paper(id="1v1", title="t", abstract="a")
    assert trust.assess(preprint, enabled=["peer_review"]).signals[0].status == trust.WARN


def test_peer_review_flags_stale_unaccepted():
    now = datetime.now(timezone.utc)
    old = Paper(id="1v1", title="t", abstract="a",
                published=now.replace(year=now.year - 4))
    sig = trust.assess(old, enabled=["peer_review"]).signals[0]
    assert sig.status == trust.WARN and "still v1" in sig.note


def test_flags_carry_evidence_and_confidence():
    paper = Paper(
        id="1", title="t",
        abstract="A novel state-of-the-art method that significantly outperforms all.",
    )
    sig = trust.assess(paper, enabled=["evidence"]).signals[0]
    assert sig.status == trust.FLAG
    assert sig.evidence  # the exact claim words that tripped it
    assert 0.0 < sig.confidence <= 1.0


def test_paper_version_parsing():
    assert Paper(id="2401.01234v3", title="t", abstract="a").version == 3
    assert Paper(id="2401.01234", title="t", abstract="a").version == 1
