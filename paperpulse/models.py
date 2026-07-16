"""Shared data structures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # trust imports models, so this can't be a runtime import
    from .trust import TrustReport


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
    # arXiv metadata used by the peer-review signal.
    comment: str = ""       # author's note, e.g. "Accepted at NeurIPS 2024"
    journal_ref: str = ""   # set once formally published

    def as_text(self) -> str:
        """Text used for embedding: title carries most of the signal, so we
        repeat it once to give it a little extra weight over the abstract."""
        return f"{self.title}. {self.title}. {self.abstract}".strip()

    @property
    def version(self) -> int:
        """arXiv version number from the id suffix (``...v3`` -> 3); 1 if absent."""
        m = re.search(r"v(\d+)$", self.id)
        return int(m.group(1)) if m else 1


@dataclass
class RankedPaper:
    """A paper together with its relevance score, summary, and trust report."""

    paper: Paper
    score: float
    summary: Optional[str] = None
    # Populated with a paperpulse.trust.TrustReport when trust signals are on.
    trust: Optional["TrustReport"] = None
    # Mean similarity to nearest neighbours in the same batch (novelty proxy).
    crowding: Optional[float] = None
    # Detected market/region tags (B1), e.g. ["USA"] or ["Global/Unspecified"].
    regions: list[str] = field(default_factory=list)
    # Set when this paper's region isn't in already_tested_regions for a
    # matched known/tried topic (B2) -- a green "worth exploring" note.
    region_note: str = ""
