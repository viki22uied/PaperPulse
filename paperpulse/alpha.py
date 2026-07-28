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
    # Basis points are the standard unit for anomaly returns -- "48 bp per
    # month" is a precise, checkable claim and must not read as unquantified.
    "basis points": r"(\d+(?:\.\d+)?)\s*(?:bps?|basis\s+points?)\b",
    "monthly return": r"(\d+(?:\.\d+)?)\s*%\s*per\s+month|monthly\s+returns?\s+of\s+(\d+(?:\.\d+)?)\s*%",
    "alpha": r"\balphas?\s*(?:of\s+|=\s*|:\s*)(-?\d+(?:\.\d+)?\s*%?)",
    "R²": r"\bR\^?2\s*(?:of\s+|=\s*|:\s*)?(\d*\.\d+)",
    "information ratio": r"\binformation\s+ratios?\s*(?:of\s+|=\s*|:\s*)?(\d+\.\d+)",
    "p-value": r"\bp\s*[<=]\s*(0?\.\d+)",
}

# --- universe ---------------------------------------------------------------
UNIVERSE_PATTERNS = {
    "US equities": r"\b(?:US|U\.S\.|American)\s+(?:stock|equit|share)|NYSE|NASDAQ|S&P\s*500|Russell\s*\d+",
    "global equities": r"\b(?:international|global|cross[- ]countr|world)\s+(?:stock|equit|market)",
    # "DeFi" needs the trailing boundary: without it, case-insensitive matching
    # finds "defi" inside "define"/"defined" and tags every theory paper crypto.
    "crypto": r"\b(?:crypto(?:currenc)?|bitcoin|ethereum|digital asset|"
              r"stablecoin|USDT|USDC|perpetual (?:swap|future)|DeFi\b)",
    "FX": r"\b(?:foreign exchange|currency|FX)\s+(?:market|rate|carry)?",
    "fixed income": r"\b(?:bond|treasur|fixed[- ]income|credit spread|yield curve)",
    "commodities": r"\b(?:commodit|futures\s+market|crude oil|gold)",
    "options": r"\b(?:option|implied volatilit|derivative)",
}

# Checked only when no more specific equity market matched, so a paper about
# "long-short equity portfolios" isn't left with no universe at all.
_GENERIC_EQUITIES = re.compile(r"\b(?:stocks?|equit(?:y|ies)|share prices?)\b", re.I)

# "from 1990 to 2020", "1990-2020", "over 1993--2019"
_PERIOD = re.compile(
    r"\b(?:from\s+)?((?:19|20)\d{2})\s*(?:to|through|[-–—]{1,2})\s*((?:19|20)\d{2})\b"
)
# Half-open windows: papers often bound a sample on one side only
# ("post-2005", "since 1990", "through 2005", "2006 onward").
_PERIOD_OPEN = re.compile(
    r"\b(?:(post|since|after|pre|before|through|until)[\s-]+((?:19|20)\d{2})"
    r"|((?:19|20)\d{2})\s+(onward|onwards))\b",
    re.I,
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
    r"bank|capital|liquidit|systemic risk|bubble|monetary|inflation|"
    r"arbitrage|derivativ|option|futures|microstructure|order flow|"
    r"sharpe|backtest|valuation|dividend)", re.I
)


@dataclass
class AlphaCard:
    """The testable content of a paper, as stated in its abstract."""

    claim: str = ""                                   # "X predicts Y"
    data_sources: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)  # ["Sharpe 1.82", "t-stat 3.10"]
    universe: list[str] = field(default_factory=list)
    period: str = ""                                  # "1990-2020"
    # True when the card read the PDF, not just the abstract -- a missing field
    # then means "the paper doesn't say", not "the abstract didn't mention it".
    from_full_text: bool = False

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
            # Patterns may offer several alternatives; take whichever captured.
            value = next((g for g in match.groups() if g), "").strip()
            if value:
                found.append(f"{label} {value}")
    return found


def _find_universe(text: str) -> list[str]:
    found = [
        name for name, pattern in UNIVERSE_PATTERNS.items()
        if re.search(pattern, text, re.I)
    ]
    if not any(name.endswith("equities") for name in found) and _GENERIC_EQUITIES.search(text):
        found.append("equities")
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
    """Build an :class:`AlphaCard` from a paper's abstract, and its PDF text if
    you have it (see :func:`paperpulse.fulltext.fetch_full_text`).

    Returns ``None`` when the paper isn't making a market claim at all -- there
    is no alpha to card. A *vague* card is a different and useful answer: the
    paper is about markets but names no data, effect size, universe, or period,
    so there is nothing you could go replicate.

    Numbers and claims are only ever read from the paper's *own* sections: the
    abstract plus full text with related-work, literature-review and reference
    sections removed. Without that, the first "Sharpe ratio of 0.8" in a
    40-page PDF is usually a rival paper's result being quoted, and the card
    would confidently attribute it here. Dataset and universe mentions are read
    from everything, since naming CRSP anywhere is evidence the paper uses it."""
    abstract = f"{paper.title}. {paper.abstract}"
    if full_text:
        from .fulltext import own_work_text

        # Attribution-safe: this paper's own claims and numbers.
        claim_text = f"{abstract} {own_work_text(full_text)}"
        # Attribution-agnostic: what data/markets are in play.
        mention_text = f"{abstract} {full_text}"
    else:
        claim_text = mention_text = abstract

    if not _FINANCE_HINT.search(mention_text):
        return None

    period = ""
    match = _PERIOD.search(claim_text)
    if match:
        start, end = match.group(1), match.group(2)
        if int(end) > int(start):  # "2020-2019" is a typo, not a sample window
            period = f"{start}-{end}"
    if not period:
        open_match = _PERIOD_OPEN.search(claim_text)
        if open_match:
            word, year, year_after, onward = (
                open_match.group(1), open_match.group(2),
                open_match.group(3), open_match.group(4),
            )
            period = f"{word.lower()} {year}" if word else f"{year_after} {onward.lower()}"

    # Universe comes from the abstract only, which states what the paper is
    # actually about. Scanning a whole PDF for it is worse than useless: words
    # like "bond" or "currency" turn up in passing in almost any finance paper,
    # so a crypto-regulation study comes back claiming to cover four asset
    # classes. If the abstract names no market, "not stated" is the honest
    # answer -- unlike datasets and effect sizes, which the body reports
    # precisely and abstracts routinely omit.
    return AlphaCard(
        claim=_find_claim(claim_text),
        data_sources=[
            name for name, pattern in DATA_SOURCES.items()
            if re.search(pattern, mention_text, re.I)
        ],
        effects=_find_effects(claim_text),
        universe=_find_universe(abstract),
        period=period,
        from_full_text=bool(full_text),
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
    assert card is not None
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
