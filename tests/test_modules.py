"""Contradiction mapping, cross-referencing, community DB, and delivery."""

from paperpulse.community import CommunityDB
from paperpulse.contradiction import contradiction_map
from paperpulse.crossref import code_to_text, similar_papers
from paperpulse.delivery.rss import render_rss
from paperpulse.embeddings import HashingBackend
from paperpulse.models import Paper, RankedPaper


def _backend():
    return HashingBackend(dim=4096)


def test_contradiction_map_finds_opposing_pair():
    backend = _backend()
    papers = [
        Paper(
            id="pos",
            title="Dropout improves generalization",
            abstract="Dropout consistently improves generalization and "
            "outperforms strong baselines, yielding better accuracy on image "
            "classification.",
        ),
        Paper(
            id="neg",
            title="Dropout degrades generalization",
            abstract="Dropout degrades generalization and performs worse than "
            "baselines; we observe no benefit for image classification accuracy.",
        ),
        Paper(
            id="unrelated",
            title="A study of sourdough fermentation",
            abstract="We analyze yeast activity during sourdough fermentation.",
        ),
    ]
    pairs = contradiction_map(papers, backend, similarity_threshold=0.3)
    assert any({p.a.id, p.b.id} == {"pos", "neg"} for p in pairs)


def test_code_to_text_splits_identifiers():
    text = code_to_text("def cosine_similarity(a, b):  # dot product\n    return a @ b")
    assert "cosine" in text and "similarity" in text
    assert "dot" in text and "product" in text


def test_similar_papers_ranks_relevant_first():
    backend = _backend()
    work = code_to_text("def dense_retriever_embed(query):\n    return encode(query)")
    papers = [
        Paper(id="1", title="Dense retriever embeddings", abstract="encode queries for dense retrieval"),
        Paper(id="2", title="Protein folding", abstract="alphafold protein structure prediction"),
    ]
    results = similar_papers(work, papers, backend, top_n=2)
    assert results[0].paper.id == "1"


def test_community_db_records_and_leaderboards(tmp_path):
    db = CommunityDB(tmp_path / "c.db")
    db.record_trust(
        "p1", score=0.3, badge="caution", flags=["overclaim"],
        authors=["A. Author"], venue="cs.LG",
    )
    db.record_trust(
        "p2", score=0.9, badge="clean", flags=[], authors=["B. Author"],
    )
    board = db.flag_leaderboard()
    assert board and board[0]["author"] == "A. Author"
    db.close()


def test_community_db_notes(tmp_path):
    db = CommunityDB(tmp_path / "c.db")
    assert db.get_notes("p1") == []
    db.add_note("p1", "worth re-reading", user="alice")
    db.add_note("p1", "unrelated", user="bob")
    notes = db.get_notes("p1")
    assert [n["note"] for n in notes] == ["worth re-reading", "unrelated"]
    assert db.get_notes("p1", user="alice")[0]["note"] == "worth re-reading"
    db.close()


def test_fetch_full_text_returns_none_without_pdf_url():
    from paperpulse.fulltext import fetch_full_text
    from paperpulse.models import Paper

    assert fetch_full_text(Paper(id="1", title="t", abstract="a")) is None


def test_render_rss_is_wellformed():
    from xml.etree import ElementTree as ET

    ranked = [
        RankedPaper(
            paper=Paper(id="1", title="T & U", abstract="", url="http://x/1"),
            score=0.7,
            summary="did a thing",
        )
    ]
    xml = render_rss(ranked)
    root = ET.fromstring(xml)  # raises if malformed / unescaped
    assert root.tag == "rss"
    assert root.find(".//item/title").text == "T & U"
