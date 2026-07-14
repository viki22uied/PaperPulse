"""PubMed source, via NCBI E-utilities (esearch + efetch).

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/. No key is required for light
use; set ``NCBI_API_KEY`` to raise the rate limit. We search by keyword/author,
then fetch abstracts in one batched efetch call.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from ..models import Paper
from .base import Query, register

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _get(url: str, params: dict, timeout: float) -> bytes:
    key = os.getenv("NCBI_API_KEY")
    if key:
        params = {**params, "api_key": key}
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "PaperPulse/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _article_to_paper(article: ET.Element) -> Paper | None:
    pmid_node = article.find(".//PMID")
    pmid = pmid_node.text if pmid_node is not None else None
    if not pmid:
        return None
    title_node = article.find(".//ArticleTitle")
    title = "".join(title_node.itertext()).strip() if title_node is not None else ""
    abstract_parts = [
        "".join(node.itertext()).strip()
        for node in article.findall(".//Abstract/AbstractText")
    ]
    abstract = " ".join(p for p in abstract_parts if p)

    authors = []
    for author in article.findall(".//Author"):
        last = author.findtext("LastName")
        fore = author.findtext("ForeName")
        if last:
            authors.append(" ".join(x for x in (fore, last) if x))

    year = article.findtext(".//PubDate/Year")
    published = None
    if year and year.isdigit():
        published = datetime(int(year), 1, 1, tzinfo=timezone.utc)

    return Paper(
        id=f"pmid:{pmid}",
        title=" ".join(title.split()),
        abstract=" ".join(abstract.split()),
        authors=authors,
        categories=["pubmed"],
        published=published,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    )


def fetch_recent(
    term: str, *, max_results: int = 100, timeout: float = 30.0
) -> list[Paper]:
    ids_xml = _get(
        ESEARCH,
        {"db": "pubmed", "term": term, "retmax": max_results, "sort": "date"},
        timeout,
    )
    root = ET.fromstring(ids_xml)
    ids = [node.text for node in root.findall(".//Id") if node.text]
    if not ids:
        return []
    fetch_xml = _get(
        EFETCH,
        {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
        timeout,
    )
    articles = ET.fromstring(fetch_xml).findall(".//PubmedArticle")
    papers = [_article_to_paper(a) for a in articles]
    return [p for p in papers if p is not None][:max_results]


class PubmedSource:
    name = "pubmed"

    def fetch(self, query: Query) -> list[Paper]:
        terms = list(query.keywords) or list(query.categories)
        term = " OR ".join(f"({t})" for t in terms) if terms else "review"
        if query.authors:
            authors = " OR ".join(f'"{a}"[Author]' for a in query.authors)
            term = f"({term}) AND ({authors})" if terms else authors
        return fetch_recent(term, max_results=query.max_results)


register(PubmedSource())
