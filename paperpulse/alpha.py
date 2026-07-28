"""Alpha cards: what testable claim does this paper actually make?

Relevance tells you a paper is about your area; trust tells you whether to
believe it. Neither answers the question a systematic researcher actually asks
next: *is there an implementable signal in here, and what would it cost me to
test it?*

An ``AlphaCard`` pulls that out of the abstract -- the predictor and what it is
claimed to predict, the datasets named, the reported effect sizes, and the
sample universe and period -- then rates how *testable* the claim is from how
much of that the authors actually specified. A paper reporting a Sharpe ratio on
a named dataset over a stated period is something you can go replicate; one
claiming "improved performance" on unnamed data is not, however clean its trust
badge.

ponytail: deterministic regex over the abstract, no LLM and no network, matching
the rest of the offline core. It reads what authors chose to put in the
abstract, so absence of a field means "not stated there", not "not in the
paper" -- the full text may say more (see ``paperpulse.fulltext``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Paper

# --- data sources -----------------------------------------------------------
# Named datasets/vendors a quant would need access to. Matching these tells you
# the replication cost up front: CRSP/Compustat means a WRDS subscription,
# Binance means a free public API.
DATA_SOURCES = {
    "CRSP": r"\bCRSP\b",
    "Compustat": r"\bCompustat\b",
    "TAQ": r"\bTAQ\b",
    "WRDS": r"\bWRDS\b",
    "IBES": r"\bI/?B/?E/?S\b",
    "Bloomberg": r"\bBloomberg\b",
    "Refinitiv": r"\bRefinitiv|Datastream|Thomson Reuters\b",
    "OptionMetrics": r"\bOptionMetrics\b",
    "LOBSTER": r"\bLOBSTER\b",
    "Binance": r"\bBinance\b",
    "Coinbase": r"\bCoinbase\b",
    "Kaggle": r"\bKaggle\b",
    "FRED": r"\bFRED\b",
    "EDGAR": r"\bEDGAR\b|\bSEC filings?\b",
    "Fama-French": r"\bFama[- ]French\b",
    "TRACE": r"\bTRACE\b",
    "Yahoo Finance": r"\bYahoo Finance\b",
}

# --- effect sizes -----------------------------------------------------------
# The numbers that make a claim checkable. Each pattern captures the value so
# the card can show it verbatim rather than paraphrasing.
EFFECT_PATTERNS = {
    "Sharpe": r"\bSharpe(?:\s+ratios?)?\s*(?:of\s+|=\s*|:\s*)?(\d+\.\d+)",
    "t-stat": r"\bt[- ]?(?:stat(?:istic)?s?|value)?\s*(?:of\s+|=\s*|:\s*)?(-?\d+\.\d+)",
    "annual return": r"(\d+(?:\.\d+)?)\s*%\s*(?:per\s+annum|annual(?:ized|ised)?|p\.a\.)",
    "alpha": r"\balphas?\s*(?:of\s+|=\s*|:\s*)(-?\d+(?:\.\d+)?\s*%?)",
    "R²": r"\bR\^?2\s*(?:of\s+|=\s*|:\s*)?(\d*\.\d+)",
    "information ratio": r"\binformation\s+ratios?\s*(?:of\s+|=\s*|:\s*)?(\d+\.\d+)",
    "p-value": r"\bp\s*[<=]\s*(0?\.\d+)",
}

# --- universe ---------------------------------------------------------------
UNIVERSE_PATTERNS = {
    "US equities": r"\b(?:US|U\.S\.|American)\s+(?:stock|equit|share)|NYSE|NASDAQ|S&P\s*500|Russell\s*\d+",
    "global equities": r"\b(?:international|global|cross[- ]countr|world)\s+(?:stock|equit|market)",
    "crypto": r"\b(?:crypto(?:currenc)?|bitcoin|ethereum|digital asset)",
    "FX": r"\b(?:foreign exchange|currency|FX)\s+(?:market|rate|carry)?",
    "fixed income": r"\b(?:bond|treasur|fixed[- ]income|credit spread|yield curve)",
    "commodities": r"\b(?:commodit|futures\s+market|crude oil|gold)",
    "options": r"\b(?:option|implied volatilit|derivative)",
}

# "from 1990 to 2020", "1990-2020", "over 1993--2019"
_PERIOD = re.compile(
    r"\b(?:from\s+)?((?:19|20)\d{2})\s*(?:to|through|[-–—]{1,2})\s*((?:19|20)\d{2})\b"
)

# "X predicts Y", "X forecasts Y" -- the core claim shape. Kept deliberately
# tight: a loose pattern here produces confident nonsense.
_PREDICTS = re.compile(
    r"([A-Za-z][\w\s,'\-]{2,60}?)\s+"
    r"(predicts?|forecasts?|explains?|is\s+(?:positively|negatively)\s+"
    r"(?:related|associated)\s+(?:to|with)|drives?)\s+"
    r"([\w\s,'\-]{2,60}?)(?=[.;,]|\s+(?:and|but|while|which|in|over|using)\b)",
    re.I,
)

# Papers that aren't making an empirical market claim at all.
_FINANCE_HINT = re.compile(
    r"\b(return|portfolio|asset|market|trading|price|volatilit|risk premi|"
    r"investor|stock|equit|hedg|alpha|factor|yield|financ|econom|credit|"
    r"bank|capital|liquidit|systemic risk|bubble|monetary|inflation)", re.I
)


@dataclass
class AlphaCard:
    """The testable content of a paper, as stated in its abstract."""

    claim: str = ""                                   # "X predicts Y"
    data_sources: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)  # ["Sharpe 1.82", "t-stat 3.10"]
    universe: list[str] = field(default_factory=list)
    period: str = ""                                  # "1990-2020"

    @property
    def testability(self) -> str:
        """How much of what you'd need to replicate this is actually stated:
        ``strong`` / ``partial`` / ``vague``."""
        score = self.testability_score
        if score >= 3:
            return "strong"
        return "partial" if score >= 2 else "vague"

    @property
    def testability_score(self) -> int:
        """Count of the four replication ingredients that are present."""
        return sum(
            bool(x) for x in (self.data_sources, self.effects, self.universe, self.period)
        )

    @property
    def missing(self) -> list[str]:
        """Replication ingredients the abstract never states -- the shopping
        list you'd have to fill in before you could test this."""
        return [
            label
            for label, present in (
                ("data source", self.data_sources),
                ("effect size", self.effects),
                ("universe", self.universe),
                ("sample period", self.period),
            )
            if not present
        ]


def _find_effects(text: str) -> list[str]:
    found: list[str] = []
    for label, pattern in EFFECT_PATTERNS.items():
        match = re.search(pattern, text, re.I)
        if match:
            value = match.group(1).strip()
            found.append(f"{label} {value}")
    return found


def _find_claim(text: str) -> str:
    match = _PREDICTS.search(text)
    if not match:
        return ""
    subject = " ".join(match.group(1).split()[-8:])  # trim runaway left context
    verb = " ".join(match.group(2).split())
    obj = " ".join(match.group(3).split())
    return f"{subject} {verb} {obj}".strip()


def extract(paper: Paper, *, full_text: str | None = None) -> AlphaCard | None:
    """Build an :class:`AlphaCard` from a paper's abstract (plus full text if
    you have it).

    Returns ``None`` when the paper isn't making a market claim at all -- there
    is no alpha to card. A *vague* card is a different and useful answer: the
    paper is about markets but names no data, effect size, universe, or period,
    so there is nothing in the abstract you could go replicate."""
    text = f"{paper.title}. {paper.abstract}" + (f" {full_text}" if full_text else "")
    if not _FINANCE_HINT.search(text):
        return None

    period = ""
    match = _PERIOD.search(text)
    if match:
        start, end = match.group(1), match.group(2)
        if int(end) > int(start):  # "2020-2019" is a typo, not a sample window
            period = f"{start}-{end}"

    return AlphaCard(
        claim=_find_claim(text),
        data_sources=[
            name for name, pattern in DATA_SOURCES.items() if re.search(pattern, text, re.I)
        ],
        effects=_find_effects(text),
        universe=[
            name for name, pattern in UNIVERSE_PATTERNS.items()
            if re.search(pattern, text, re.I)
        ],
        period=period,
    )


if __name__ == "__main__":  # smoke check
    strong = Paper(
        id="1", title="Idiosyncratic volatility and the cross-section of returns",
        abstract=(
            "Using CRSP and Compustat data for US stocks listed on NYSE and NASDAQ "
            "from 1990 to 2020, we show that idiosyncratic volatility predicts "
            "future returns. A long-short portfolio earns a Sharpe ratio of 1.24 "
            "with a t-statistic of 3.80."
        ),
    )
    card = extract(strong)
    assert card.testability == "strong", card
    assert "CRSP" in card.data_sources and "Compustat" in card.data_sources
    assert card.period == "1990-2020"
    assert "US equities" in card.universe
    assert any(e.startswith("Sharpe 1.24") for e in card.effects), card.effects
    assert "predicts" in card.claim, card.claim

    # A market paper that specifies nothing testable is "vague", not absent --
    # and the missing list is the point.
    vague = Paper(
        id="2", title="A deep learning approach to trading",
        abstract="We propose a novel neural architecture that improves trading performance.",
    )
    vague_card = extract(vague)
    assert vague_card is not None and vague_card.testability == "vague"
    assert "effect size" in vague_card.missing and "data source" in vague_card.missing

    # Not a market claim at all -> no card.
    non_finance = Paper(
        id="3", title="Attention is all you need",
        abstract="We propose the Transformer, a new network architecture for translation.",
    )
    assert extract(non_finance) is None

    print("alpha OK:", card.testability, card.effects, card.data_sources)
