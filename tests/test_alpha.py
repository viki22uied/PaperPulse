"""Alpha card extraction: what testable claim does a paper make?"""

from paperpulse import alpha
from paperpulse.digest import render_markdown
from paperpulse.models import Paper, RankedPaper


def _paper(abstract, title="A finance paper"):
    return Paper(id="1", title=title, abstract=abstract)


def test_fully_specified_paper_is_strong():
    card = alpha.extract(
        _paper(
            "Using CRSP and Compustat data on NYSE stocks from 1990 to 2020, we "
            "find that idiosyncratic volatility predicts future returns. The "
            "long-short portfolio earns a Sharpe ratio of 1.24 (t-statistic of 3.80)."
        )
    )
    assert card is not None
    assert card.testability == "strong"
    assert card.testability_score == 4
    assert card.data_sources == ["CRSP", "Compustat"]
    assert card.universe == ["US equities"]
    assert card.period == "1990-2020"
    assert "Sharpe 1.24" in card.effects
    assert "predicts" in card.claim
    assert card.missing == []


def test_market_paper_with_no_specifics_is_vague():
    """The useful case: it's about markets but there's nothing to replicate."""
    card = alpha.extract(
        _paper("We propose a novel deep model that improves trading performance.")
    )
    assert card is not None
    assert card.testability == "vague"
    assert set(card.missing) == {"data source", "effect size", "universe", "sample period"}


def test_non_market_paper_gets_no_card():
    card = alpha.extract(
        _paper(
            "We introduce a transformer architecture for machine translation.",
            title="Attention is all you need",
        )
    )
    assert card is None


def test_partial_card_lists_only_what_is_missing():
    card = alpha.extract(
        _paper("We study Bitcoin order flow using Binance trade data.")
    )
    assert card is not None
    assert card.data_sources == ["Binance"]
    assert card.universe == ["crypto"]
    assert "effect size" in card.missing and "sample period" in card.missing
    assert "data source" not in card.missing


def test_reversed_year_range_is_not_a_period():
    """'2020-2019' is a typo or an unrelated pair of numbers, not a sample."""
    card = alpha.extract(_paper("Returns on the S&P 500 from 2020 to 2019."))
    assert card is not None and card.period == ""


def test_digest_renders_alpha_block():
    paper = _paper(
        "Using CRSP data from 1990 to 2020 on NYSE stocks, momentum predicts "
        "returns with a Sharpe ratio of 0.90."
    )
    item = RankedPaper(paper=paper, score=0.5, alpha=alpha.extract(paper))
    markdown = render_markdown([item])
    assert "Alpha card" in markdown
    assert "strong" in markdown
    assert "CRSP" in markdown
    assert "Sharpe 0.90" in markdown


def test_digest_omits_alpha_block_when_no_card():
    item = RankedPaper(paper=_paper("A transformer for translation."), score=0.5)
    assert "Alpha card" not in render_markdown([item])
