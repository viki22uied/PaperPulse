"""Publication-status signal, straight from arXiv metadata.

Distinguishes formally published / venue-accepted work from preprint-only, and
flags papers that have sat on arXiv for years, still at v1, without ever landing
a venue -- a soft signal that the work may not have cleared review. All from the
``journal_ref``, ``comment``, ``published`` date and version already on Paper,
so it needs no network and no extra dependency.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models import Paper
from . import OK, WARN, Signal, signal

# Phrases authors use in the arXiv comment to announce acceptance.
_ACCEPTED = re.compile(
    r"\b(accepted|to appear|camera[- ]ready|proceedings of|published in|"
    r"neurips|icml|iclr|cvpr|eccv|iccv|acl|emnlp|naacl|aaai|kdd|sigir|www|"
    r"nature|science|journal of|transactions on|conference on)\b",
    re.I,
)
_STALE_YEARS = 2.0


def _age_years(paper: Paper) -> float | None:
    if not paper.published:
        return None
    published = paper.published
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - published).days / 365.25


@signal("peer_review")
def peer_review_signal(paper: Paper, **_) -> Signal:
    """Peer-review / venue status from arXiv metadata."""
    if paper.journal_ref:
        return Signal(
            "peer_review", OK, "Formally published.",
            evidence=paper.journal_ref, confidence=0.95,
        )
    accepted = _ACCEPTED.search(paper.comment or "")
    if accepted:
        return Signal(
            "peer_review", OK, "Author reports acceptance at a venue.",
            evidence=paper.comment, confidence=0.7,
        )

    age = _age_years(paper)
    if age is not None and age >= _STALE_YEARS and paper.version == 1:
        return Signal(
            "peer_review",
            WARN,
            f"On arXiv ~{age:.0f} years, still v1, with no venue named -- may "
            "never have cleared peer review.",
            evidence=f"published {paper.published:%Y-%m}, v1, no journal_ref",
            confidence=0.6,
        )
    return Signal(
        "peer_review", WARN, "Preprint only -- not yet peer-reviewed.",
        confidence=0.4,
    )


if __name__ == "__main__":  # smoke check
    now = datetime.now(timezone.utc)
    assert peer_review_signal(Paper(id="1", title="t", abstract="a",
                                    journal_ref="J. Finance 2023")).status == OK
    assert peer_review_signal(Paper(id="1v1", title="t", abstract="a",
                                    comment="Accepted at NeurIPS 2024")).status == OK
    old = Paper(id="1v1", title="t", abstract="a",
                published=now.replace(year=now.year - 4))
    s = peer_review_signal(old)
    assert s.status == WARN and "still v1" in s.note, s
    print("peer_review OK")
