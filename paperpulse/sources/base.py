"""Common interface for paper sources.

A source is anything that can hand back a list of :class:`Paper` given a query
spec. arXiv, bioRxiv and PubMed all implement it, and the pipeline treats them
interchangeably, so adding OpenReview or SSRN later is just another adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..models import Paper


@dataclass
class Query:
    """A source-agnostic request for recent papers."""

    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    max_results: int = 200


class Source(Protocol):
    name: str

    def fetch(self, query: Query) -> list[Paper]:
        """Return recent papers matching ``query``."""


_REGISTRY: dict[str, "Source"] = {}


def register(source: "Source") -> "Source":
    _REGISTRY[source.name] = source
    return source


def get_source(name: str) -> "Source":
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown source {name!r}; available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def available() -> list[str]:
    return sorted(_REGISTRY)
