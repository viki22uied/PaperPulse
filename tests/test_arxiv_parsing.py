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
