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


def test_community_db_trust_for(tmp_path):
    db = CommunityDB(tmp_path / "c.db")
    db.record_trust("p1", score=0.3, badge="caution", flags=["overclaim"])
    db.record_trust("p2", score=0.9, badge="clean", flags=[])
    result = db.trust_for(["p1", "p2", "missing"])
    assert result == {
        "p1": {"score": 0.3, "badge": "caution"},
        "p2": {"score": 0.9, "badge": "clean"},
    }
    assert db.trust_for([]) == {}
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


def test_fetch_full_text_uses_the_no_redirect_opener(monkeypatch):
    """A host that passes the pdf_url allowlist can still redirect off-host;
    the fetch must go through the shared no-redirect opener (netguard.py),
    not urllib's default one which follows 3xx with no re-check."""
    import sys
    import types

    from paperpulse import fulltext
    from paperpulse.models import Paper

    # This test is about the redirect guard, not PDF parsing -- stub pypdf so
    # it doesn't depend on the optional [pdf] extra being installed (CI's
    # base `pip install -e ".[dev,backtest]"` doesn't include it).
    fake_pypdf = types.ModuleType("pypdf")
    fake_pypdf.PdfReader = object  # never actually called; open() raises first
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    calls = []

    def fake_open(request, timeout):
        calls.append(request.full_url)
        raise RuntimeError("stop before actually hitting the network")

    monkeypatch.setattr(fulltext.NO_REDIRECT_OPENER, "open", fake_open)
    paper = Paper(id="1", title="t", abstract="a", pdf_url="https://arxiv.org/pdf/1.pdf")
    result = fulltext.fetch_full_text(paper)
    assert result is None  # fails soft
    assert calls == ["https://arxiv.org/pdf/1.pdf"]  # went through the guarded opener


def test_fetch_full_texts_runs_concurrently_and_skips_empty_results(monkeypatch):
    """_fetch_full_texts fans out over a thread pool now instead of fetching
    one paper at a time. Confirm: every paper's text lands under its own id
    (order-independent correctness), a paper with no text (fetch_full_text's
    own fail-soft path returns "") is left out of the dict exactly like the
    old sequential loop did, and it's actually running concurrently rather
    than just wrapping the same sequential work in an unused executor."""
    import time

    import paperpulse.pipeline as pipeline_mod
    from paperpulse.config import Config
    from paperpulse.models import Paper, RankedPaper

    def fake_fetch(paper, **_):
        time.sleep(0.05)  # long enough that sequential vs. concurrent differ
        return "" if paper.id == "empty" else f"full text of {paper.id}"

    monkeypatch.setattr("paperpulse.fulltext.fetch_full_text", fake_fetch)

    ranked = [
        RankedPaper(paper=Paper(id=pid, title="t", abstract="a"), score=0.5)
        for pid in ["a", "b", "empty", "c"]
    ]
    t0 = time.time()
    texts = pipeline_mod._fetch_full_texts(Config(), ranked)
    elapsed = time.time() - t0

    assert texts == {
        "a": "full text of a",
        "b": "full text of b",
        "c": "full text of c",
    }
    assert "empty" not in texts
    # 4 papers at 0.05s each: concurrent stays well under the 0.2s serial sum.
    assert elapsed < 0.19


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
