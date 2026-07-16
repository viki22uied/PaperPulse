"""Parsing of the arXiv Atom feed, using a captured sample (no network)."""

from xml.etree import ElementTree as ET

from paperpulse.sources.arxiv import _NS, _entry_to_paper

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <updated>2024-01-15T10:00:00Z</updated>
    <published>2024-01-10T09:30:00Z</published>
    <title>Learning Dense Retrievers
      with Contrastive Objectives</title>
    <summary>  We propose a contrastive method for training dense
      retrievers.   It works well.</summary>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link href="http://arxiv.org/abs/2401.01234v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.01234v1" rel="related" type="application/pdf"/>
    <category term="cs.IR"/>
    <category term="cs.CL"/>
  </entry>
</feed>
"""


def _entry():
    root = ET.fromstring(SAMPLE)
    return root.find("atom:entry", _NS)


def test_entry_fields():
    paper = _entry_to_paper(_entry())
    assert paper.id == "2401.01234v1"
    assert paper.title == "Learning Dense Retrievers with Contrastive Objectives"
    assert "contrastive method" in paper.abstract
    assert "  " not in paper.abstract  # whitespace collapsed
    assert paper.authors == ["Ada Lovelace", "Alan Turing"]
    assert paper.categories == ["cs.IR", "cs.CL"]
    assert paper.pdf_url == "http://arxiv.org/pdf/2401.01234v1"
    assert paper.published is not None and paper.published.year == 2024


def test_as_text_weights_title():
    paper = _entry_to_paper(_entry())
    text = paper.as_text()
    assert text.count("Learning Dense Retrievers") == 2


def test_fetch_page_retries_once_on_a_transient_timeout(monkeypatch):
    """A single read timeout (how arXiv's stall surfaced in the scheduled
    digest) must be retried, not propagated -- it was taking down the whole run.
    """
    from paperpulse.sources import arxiv

    _ATOM = (
        b'<?xml version="1.0"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom"'
        b' xmlns:arxiv="http://arxiv.org/schemas/atom"></feed>'
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _ATOM

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("The read operation timed out")
        return _Resp()

    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)  # don't wait in tests
    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    papers = arxiv._fetch_page("cat:cs.LG", 0, 10, timeout=1.0)
    assert calls["n"] == 2  # failed once, retried, succeeded
    assert papers == []


def test_fetch_page_raises_when_timeout_persists(monkeypatch):
    """A persistent outage still surfaces after the retry is exhausted."""
    import pytest

    from paperpulse.sources import arxiv

    def always_timeout(request, timeout=None):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)
    monkeypatch.setattr(arxiv.urllib.request, "urlopen", always_timeout)

    with pytest.raises(TimeoutError):
        arxiv._fetch_page("cat:cs.LG", 0, 10, timeout=1.0)
