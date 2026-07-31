"""Extractive summariser, digest rendering, and config round-trips."""

from datetime import date
from pathlib import Path

from paperpulse.config import Config
from paperpulse.digest import render_markdown
from paperpulse.models import Paper, RankedPaper
from paperpulse.profile import InterestProfile
from paperpulse.embeddings import HashingBackend
from paperpulse.summarize import extractive_summary


def test_extractive_summary_limits_sentences():
    paper = Paper(
        id="1",
        title="X",
        abstract=(
            "Retrieval is important. We propose a new method. "
            "The method uses embeddings. Experiments show gains. "
            "We release code and data."
        ),
    )
    summary = extractive_summary(paper, max_sentences=2)
    # Two sentences means one sentence break at most.
    assert summary.count(".") <= 2
    assert summary  # non-empty


def test_short_abstract_returned_whole():
    paper = Paper(id="1", title="X", abstract="One sentence only.")
    assert extractive_summary(paper) == "One sentence only."


def test_render_markdown_contains_papers():
    ranked = [
        RankedPaper(
            paper=Paper(
                id="2401.1",
                title="A Great Paper",
                abstract="...",
                authors=["A. Author"],
                categories=["cs.LG"],
                url="http://arxiv.org/abs/2401.1",
            ),
            score=0.83,
            summary="It is great.",
        )
    ]
    md = render_markdown(ranked, on_date=date(2024, 1, 1))
    assert "A Great Paper" in md
    assert "0.83" in md
    assert "http://arxiv.org/abs/2401.1" in md


def test_empty_digest_is_friendly():
    md = render_markdown([], on_date=date(2024, 1, 1))
    assert "No papers" in md


def test_digest_tiers_by_batch_relative_percentile():
    """A cosine score of 0.30 with nothing else in the batch to compare
    against is meaningless on an absolute 0-1 scale -- the digest should
    rank/group papers by where they sit within *this* batch, and the raw
    score stays visible for transparency."""
    ranked = [
        RankedPaper(paper=Paper(id="hi", title="High relevance", abstract="..."), score=0.30),
        RankedPaper(paper=Paper(id="mid", title="Mid relevance", abstract="..."), score=0.15),
        RankedPaper(paper=Paper(id="lo", title="Low relevance", abstract="..."), score=0.01),
    ]
    md = render_markdown(ranked, on_date=date(2024, 1, 1))
    assert "## Quick scan" in md
    assert "## Strongest matches" in md
    assert "## Lower relevance" in md
    # Raw scores still printed, not just the percentile bucket.
    assert "0.30" in md and "0.15" in md and "0.01" in md
    # The top scorer must appear before the bottom scorer in the rendered text.
    assert md.index("High relevance") < md.index("Low relevance")


def test_digest_hygiene_notes_are_separated_from_flags():
    from paperpulse import trust as trust_mod

    paper = Paper(id="1", title="A preprint", abstract="We study something.")
    report = trust_mod.assess(paper, enabled=["reproducibility", "peer_review"])
    item = RankedPaper(paper=paper, score=0.5, trust=report)
    md = render_markdown([item], on_date=date(2024, 1, 1))
    assert "Metadata:" in md
    # Neither hygiene flag should render as a bulleted **WARN** flag line.
    assert "**WARN** *reproducibility*" not in md
    assert "**WARN** *peer_review*" not in md


def test_config_roundtrip(tmp_path: Path):
    cfg = Config(categories=["q-fin.PM"], top_n=7)
    path = tmp_path / "c.yaml"
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.categories == ["q-fin.PM"]
    assert loaded.top_n == 7


def test_profile_serialisation_roundtrip():
    backend = HashingBackend(dim=1024)
    profile = InterestProfile.from_text("embeddings", backend)
    profile.update(liked=backend.encode(["retrieval embeddings"]))
    restored = InterestProfile.from_dict(profile.to_dict())
    assert restored.description == profile.description
    assert restored.n_feedback == profile.n_feedback
    assert (restored.vector == profile.vector).all()
