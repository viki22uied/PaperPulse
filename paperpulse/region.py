"""Region/market auto-tagging (B1).

Keyword-based, deterministic, offline: scans a paper's title+abstract for
well-known index/market names and returns the region(s) it plausibly covers.
A paper naming no recognizable market gets tagged "Global/Unspecified" rather
than guessed at -- that's still useful to surface (B2 treats it as an
untested-region candidate), just not confidently regional.
"""

from __future__ import annotations

import re

UNSPECIFIED = "Global/Unspecified"

REGION_KEYWORDS: dict[str, list[str]] = {
    "USA": [
        r"\bs&p ?500\b", r"\brussell ?(1000|2000|3000)\b", r"\bnasdaq\b",
        r"\bnyse\b", r"\bdow jones\b", r"\bu\.?s\.? equit", r"\bunited states\b",
        r"\bamerican equit",
    ],
    "EUR": [
        r"\bftse\b", r"\bdax\b", r"\beuro ?stoxx\b", r"\bcac ?40\b",
        r"\beurozone\b", r"\beuropean (?:equit|market|stock)",
    ],
    "CHN": [
        r"\bcsi ?300\b", r"\bshanghai\b", r"\bshenzhen\b", r"\ba-shares?\b",
        r"\bchinese (?:equit|market|stock)", r"\bchina'?s? (?:equit|market|stock)",
    ],
    "IND": [
        r"\bnifty\b", r"\bsensex\b", r"\bbse\b", r"\bnse\b",
        r"\bindian (?:equit|market|stock)",
    ],
}

_COMPILED = {
    region: re.compile("|".join(patterns), re.I)
    for region, patterns in REGION_KEYWORDS.items()
}


def detect_regions(text: str) -> list[str]:
    hits = [region for region, pattern in _COMPILED.items() if pattern.search(text)]
    return sorted(hits) if hits else [UNSPECIFIED]


__all__ = ["detect_regions", "REGION_KEYWORDS", "UNSPECIFIED"]
