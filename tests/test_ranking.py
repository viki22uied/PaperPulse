"""Ranking and profile behaviour, using the offline hashing backend."""

from paperpulse.embeddings import HashingBackend
from paperpulse.models import Paper
from paperpulse.profile import InterestProfile
from paperpulse.rank import rank_papers


def _backend():
    return HashingBackend(dim=4096)


def _paper(pid, title, abstract):
    return Paper(id=pid, title=title, abstract=abstract)


def test_relevant_paper_outranks_irrelevant():
    backend = _backend()
    profile = InterestProfile.from_text(
        "dense retrieval and text embeddings for natural language processing",
        backend,
    )
    papers = [
        _paper(
            "1",
            "A survey of dense retrieval with learned text embeddings",
            "We study embedding models for retrieval in natural language "
            "processing and benchmark dense retrieval systems.",
        ),
        _paper(
            "2",
            "Photonic crystals for terahertz waveguides",
            "We fabricate photonic crystal structures and measure terahertz "
            "transmission through silicon waveguides.",
        ),
    ]
    ranked = rank_papers(papers, profile, backend, top_n=2, diversity=0.0)
    assert ranked[0].paper.id == "1"
    assert ranked[0].score > ranked[1].score


def test_min_score_filters_everything():
    backend = _backend()
    profile = InterestProfile.from_text("quantum chromodynamics", backend)
    papers = [_paper("1", "A recipe for sourdough bread", "Flour, water, salt.")]
    ranked = rank_papers(papers, profile, backend, top_n=5, min_score=0.9)
    assert ranked == []


def test_feedback_moves_profile_toward_liked():
    backend = _backend()
    profile = InterestProfile.from_text("machine learning", backend)
    liked = backend.encode(
        ["graph neural networks for molecular property prediction"]
    )
    before = float(profile.vector @ liked[0])
    profile.update(liked=liked)
    after = float(profile.vector @ liked[0])
    assert after > before
    assert profile.n_feedback == 1


def test_avoid_vector_demotes_matching_paper():
    from paperpulse.rank import score_papers

    backend = _backend()
    profile = InterestProfile.from_text("equity factor research", backend)
    papers = [
        _paper(
            "board",
            "Board diversity and firm performance",
            "We study board gender diversity and its relation to firm "
            "performance and stock returns.",
        ),
    ]
    avoid_matrix = backend.encode(["board diversity, gender diversity board composition"])
    avoid_vector = avoid_matrix[0]

    scores_off, _ = score_papers(papers, profile, backend)
    scores_on, _ = score_papers(
        papers, profile, backend, avoid_vector=avoid_vector, avoid_weight=1.0
    )
    assert scores_on[0] < scores_off[0]


def test_diversity_avoids_near_duplicates():
    backend = _backend()
    profile = InterestProfile.from_text("text embeddings", backend)
    papers = [
        _paper("a", "Text embeddings for search", "dense text embeddings search"),
        _paper("b", "Text embeddings for search v2", "dense text embeddings search"),
        _paper(
            "c",
            "Sparse lexical retrieval with BM25 variants",
            "we revisit sparse lexical retrieval and bm25 weighting schemes",
        ),
    ]
    # With high diversity, the second slot should not be the near-duplicate "b".
    ranked = rank_papers(papers, profile, backend, top_n=2, diversity=0.9)
    picked = {r.paper.id for r in ranked}
    assert "c" in picked
