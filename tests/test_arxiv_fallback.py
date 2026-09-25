"""Fallback to arXiv's daily listing feed when the search API refuses us.

The scheduled digest failed on 2026-09-14..24 with HTTP 429 (after every
retry) and then HTTP 406 from export.arxiv.org -- the API blocking GitHub's
shared runner IPs. Each status code got its own fix; this covers the class:
any API refusal falls back to rss.arxiv.org, a separate service.
"""

import urllib.error
from xml.etree import ElementTree as ET

import pytest

from paperpulse.sources import arxiv
from paperpulse.sources.base import Query

LISTING = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:dc="http://purl.org/dc/elements/1.1/">
  <entry>
    <id>oai:arXiv.org:2409.11111v1</id>
    <title>Contrastive Retrieval
      at Scale</title>
    <updated>2026-09-24T00:00:00-04:00</updated>
    <link href="https://arxiv.org/abs/2409.11111" rel="alternate" type="text/html"/>
    <summary>arXiv:2409.11111v1 Announce Type: new
Abstract: We train dense retrievers   contrastively.</summary>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.IR" scheme="http://arxiv.org/schemas/atom"/>
    <published>2026-09-24T00:00:00-04:00</published>
    <arxiv:announce_type>new</arxiv:announce_type>
    <dc:creator>Ada Lovelace, Alan Turing</dc:creator>
  </entry>
  <entry>
    <id>oai:arXiv.org:2409.22222v1</id>
    <title>Speech Tokenizers</title>
    <link href="https://arxiv.org/abs/2409.22222" rel="alternate" type="text/html"/>
    <summary>arXiv:2409.22222v1 Announce Type: cross
Abstract: Audio things.</summary>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <published>2026-09-24T00:00:00-04:00</published>
    <arxiv:announce_type>cross</arxiv:announce_type>
    <dc:creator>Grace Hopper</dc:creator>
  </entry>
  <entry>
    <id>oai:arXiv.org:2301.00001v3</id>
    <title>An Old Paper, Revised</title>
    <summary>arXiv:2301.00001v3 Announce Type: replace
Abstract: Revised.</summary>
    <published>2026-09-24T00:00:00-04:00</published>
    <arxiv:announce_type>replace</arxiv:announce_type>
    <dc:creator>Someone</dc:creator>
  </entry>
</feed>
"""


class _Resp:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def _http_error(request, code):
    return urllib.error.HTTPError(request.full_url, code, "no", {}, None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(arxiv.time, "sleep", lambda *_: None)


def test_listing_entries_parse_and_skip_replacements():
    root = ET.fromstring(LISTING)
    papers = [arxiv._listing_entry_to_paper(e) for e in root.findall("atom:entry", arxiv._NS)]
    new, cross, replaced = papers
    assert replaced is None
    assert new is not None and cross is not None
    assert new.id == "2409.11111v1"
    assert new.title == "Contrastive Retrieval at Scale"
    assert new.abstract == "We train dense retrievers contrastively."
    assert new.authors == ["Ada Lovelace", "Alan Turing"]
    assert new.categories == ["cs.LG", "cs.IR"]
    assert new.url == "https://arxiv.org/abs/2409.11111"
    assert new.pdf_url == "https://arxiv.org/pdf/2409.11111v1"
    assert new.published is not None and new.published.utcoffset().total_seconds() == 0
    assert new.published.hour == 4  # 00:00 -04:00 in UTC


def test_406_from_the_api_falls_back_to_the_listing(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout=None):
        urls.append(request.full_url)
        if "export.arxiv.org" in request.full_url:
            raise _http_error(request, 406)
        return _Resp(LISTING)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    papers = arxiv.ArxivSource().fetch(Query(categories=["cs.LG", "q-fin.*"]))
    assert [p.id for p in papers] == ["2409.11111v1", "2409.22222v1"]
    assert urls[-1] == "https://rss.arxiv.org/atom/cs.LG+q-fin"


def test_fallback_applies_keyword_filter_and_max_results(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if "export.arxiv.org" in request.full_url:
            raise _http_error(request, 429)
        return _Resp(LISTING)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    source = arxiv.ArxivSource()

    only_audio = source.fetch(Query(categories=["cs.CL"], keywords=["audio"]))
    assert [p.id for p in only_audio] == ["2409.22222v1"]
    assert len(source.fetch(Query(categories=["cs.LG"], max_results=1))) == 1


def test_original_api_error_surfaces_when_listing_also_fails(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if "export.arxiv.org" in request.full_url:
            raise _http_error(request, 406)
        raise _http_error(request, 500)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError) as info:
        arxiv.ArxivSource().fetch(Query(categories=["cs.LG"]))
    assert info.value.code == 406


def test_api_request_asks_for_atom(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen.update(request.headers)
        return _Resp(b'<feed xmlns="http://www.w3.org/2005/Atom"/>')

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    arxiv._fetch_page("cat:cs.LG", 0, 10, timeout=1.0)
    assert seen.get("Accept") == "application/atom+xml"
