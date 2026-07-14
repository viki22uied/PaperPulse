"""Shared data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Paper:
    """A single arXiv paper."""

    id: str
    title: str
    abstract: str
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    published: Optional[datetime] = None
    updated: Optional[datetime] = None
    url: str = ""
    pdf_url: str = ""

    def as_text(self) -> str:
        """Text used for embedding: title carries most of the signal, so we
        repeat it once to give it a little extra weight over the abstract."""
        return f"{self.title}. {self.title}. {self.abstract}".strip()


@dataclass
class RankedPaper:
    """A paper together with its relevance score, summary, and trust report."""

    paper: Paper
    score: float
    summary: Optional[str] = None
    # Populated with a paperpulse.trust.TrustReport when trust signals are on.
    trust: Optional[object] = None
    # Mean similarity to nearest neighbours in the same batch (novelty proxy).
    crowding: Optional[float] = None
