"""Parsing of OpenAlex works into Paper objects for the SSRN adapter (C2),
using a captured sample response -- no network involved."""

from paperpulse.sources.ssrn import SSRN_SOURCE_ID, _reconstruct_abstract, _work_to_paper

SAMPLE_WORK = {
    "id": "https://openalex.org/W1234567890",
    "display_name": "Board Diversity and Firm Performance: Evidence from SSRN",
    "publication_date": "2026-03-01",
    "authorships": [
        {"author": {"display_name": "Jane Doe"}},
        {"author": {"display_name": "John Smith"}},
    ],
    "topics": [{"display_name": "Corporate Governance"}],
    "primary_location": {"landing_page_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1234567890"},
    "abstract_inverted_index": {
        "We": [0], "study": [1], "board": [2], "diversity": [3], "and": [4], "returns.": [5],
    },
}


def test_reconstruct_abstract_orders_by_position():
    text = _reconstruct_abstract(SAMPLE_WORK["abstract_inverted_index"])
    assert text == "We study board diversity and returns."


def test_reconstruct_abstract_handles_missing_index():
    assert _reconstruct_abstract(None) == ""


def test_work_to_paper_fields():
    paper = _work_to_paper(SAMPLE_WORK)
    assert paper.id == "openalex:W1234567890"
    assert paper.title == "Board Diversity and Firm Performance: Evidence from SSRN"
    assert paper.authors == ["Jane Doe", "John Smith"]
    assert paper.categories == ["Corporate Governance"]
    assert paper.published is not None and paper.published.year == 2026
    assert paper.url.startswith("https://papers.ssrn.com")
    assert "board diversity" in paper.abstract


def test_work_to_paper_skips_entries_without_id():
    assert _work_to_paper({"display_name": "no id"}) is None


def test_source_filters_by_ssrn_id(monkeypatch):
    from paperpulse.sources import ssrn as ssrn_mod
    from paperpulse.sources.base import Query

    captured = {}

    def fake_get(params, timeout):
        captured.update(params)
        return {"results": [SAMPLE_WORK]}

    monkeypatch.setattr(ssrn_mod, "_get", fake_get)
    papers = ssrn_mod.SSRNSource().fetch(Query(keywords=["board diversity"], max_results=5))
    assert len(papers) == 1
    assert SSRN_SOURCE_ID in captured["filter"]
    assert captured["search"] == "board diversity"
