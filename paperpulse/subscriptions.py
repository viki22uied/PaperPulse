"""Subscriptions: track a specific author, paper, or subfield over time.

A subscription is just a named saved query. The pipeline can run each one and
report a "what changed" diff against the last time it ran, so you can follow a
narrow topic without re-specifying it every day.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .sources import Query


@dataclass
class Subscription:
    name: str
    source: str = "arxiv"
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    max_results: int = 100
    # Ids seen on the previous run, for diffing.
    last_seen: list[str] = field(default_factory=list)

    def to_query(self) -> Query:
        return Query(
            categories=self.categories,
            keywords=self.keywords,
            authors=self.authors,
            max_results=self.max_results,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "categories": self.categories,
            "keywords": self.keywords,
            "authors": self.authors,
            "max_results": self.max_results,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription":
        return cls(
            name=data["name"],
            source=data.get("source", "arxiv"),
            categories=list(data.get("categories", [])),
            keywords=list(data.get("keywords", [])),
            authors=list(data.get("authors", [])),
            max_results=int(data.get("max_results", 100)),
            last_seen=list(data.get("last_seen", [])),
        )
