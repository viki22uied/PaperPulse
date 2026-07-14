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
