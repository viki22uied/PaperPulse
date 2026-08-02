"""BibTeX export and the shared digest JSON serializer (paperpulse export,
`paperpulse run --format json`, and GET /api/digest all go through these)."""

from datetime import datetime, timezone

from paperpulse.export import digest_to_bibtex, to_bibtex
from paperpulse.models import Paper, RankedPaper
from paperpulse.pipeline import DigestResult
from paperpulse.serialize import digest_to_dict
from paperpulse import trust as trust_mod


def _paper(id="2401.01234v2", **kw):
    kw.setdefault("title", "Attention Is All You Need Again")
    kw.setdefault("abstract", "We revisit attention.")
    kw.setdefault("authors", ["Ada Lovelace", "Alan Turing"])
    kw.setdefault("published", datetime(2024, 1, 15, tzinfo=timezone.utc))
    kw.setdefault("url", "https://arxiv.org/abs/2401.01234v2")
    return Paper(id=id, **kw)


def test_to_bibtex_arxiv_paper_gets_eprint_fields():
    paper = _paper(categories=["cs.LG"])
    bib = to_bibtex(paper)
    assert bib.startswith("@misc{lovelace2024attention,")
    assert "eprint = {2401.01234}," in bib
    assert "archivePrefix = {arXiv}," in bib
    assert "primaryClass = {cs.LG}," in bib
    assert "year = {2024}," in bib
    assert "author = {Ada Lovelace and Alan Turing}," in bib


def test_to_bibtex_non_arxiv_paper_falls_back_to_generic_entry():
    paper = _paper(id="pmid:12345678", url="https://pubmed.ncbi.nlm.nih.gov/12345678")
    bib = to_bibtex(paper)
    assert "eprint" not in bib
    assert "archivePrefix" not in bib
    assert "url = {https://pubmed.ncbi.nlm.nih.gov/12345678}," in bib


def test_to_bibtex_escapes_braces_and_handles_missing_fields():
    paper = Paper(id="pmid:1", title="A {weird} title", abstract="", authors=[])
    bib = to_bibtex(paper)
    assert "A \\{weird\\} title" in bib
    assert "author = {Unknown}," in bib
    assert bib.startswith("@misc{anon")  # no author -> "anon" key stem, no year -> "nd"


def test_digest_to_bibtex_joins_multiple_entries_with_blank_line():
    ranked = [
        RankedPaper(paper=_paper(id="2401.00001"), score=0.5),
        RankedPaper(paper=_paper(id="2401.00002"), score=0.4),
    ]
    out = digest_to_bibtex(ranked)
    assert out.count("@misc{") == 2
    assert "\n\n@misc{" in out


def test_digest_to_dict_shape():
    paper = _paper()
    report = trust_mod.assess(paper, enabled=["overclaim"])
    item = RankedPaper(paper=paper, score=0.42, summary="s", trust=report, why_rank="closest to X")
    result = DigestResult(markdown="", ranked=[item], contradictions=[])

    out = digest_to_dict(result, include_market_quotes=False)
    assert out["contradictions"] == []
    assert len(out["papers"]) == 1
    p = out["papers"][0]
    assert p["id"] == paper.id
    assert p["score"] == 0.42
    assert p["why_rank"] == "closest to X"
    assert p["quotes"] == []  # market lookup skipped
    assert p["trust"]["badge"] == report.badge
    assert "hygiene_notes" in p["trust"]


def test_digest_to_dict_market_quotes_are_opt_in(monkeypatch):
    from paperpulse import serialize

    calls = []
    monkeypatch.setattr(
        "paperpulse.market.enrich", lambda text: calls.append(text) or [{"ticker": "SPY"}]
    )
    item = RankedPaper(paper=_paper(), score=0.1)
    result = DigestResult(markdown="", ranked=[item], contradictions=[])

    out_off = serialize.digest_to_dict(result, include_market_quotes=False)
    assert out_off["papers"][0]["quotes"] == []
    assert calls == []

    out_on = serialize.digest_to_dict(result, include_market_quotes=True)
    assert out_on["papers"][0]["quotes"] == [{"ticker": "SPY"}]
    assert calls  # market.enrich was actually called this time
