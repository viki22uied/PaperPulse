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


# --- full text (pdf extra) --------------------------------------------------

_PDF_TEXT = """Introduction
We revisit momentum in equity markets.

Related Work
Jegadeesh and Titman report a Sharpe ratio of 0.55 for cross-sectional momentum.

Data
We use CRSP monthly files from 1993 to 2019 for NYSE-listed names.

Results
Our long-short strategy earns a Sharpe ratio of 1.87.

References
Some Other Author. 2001. A different paper.
"""


def test_full_text_fills_fields_the_abstract_omits():
    paper = _paper("We revisit momentum in equity markets.", title="Momentum revisited")
    thin = alpha.extract(paper)
    assert thin is not None and thin.testability_score < 2

    rich_card = alpha.extract(paper, full_text=_PDF_TEXT)
    assert rich_card is not None
    assert rich_card.from_full_text is True
    assert rich_card.data_sources == ["CRSP"]
    assert rich_card.period == "1993-2019"
    assert rich_card.testability == "strong"


def test_effects_are_not_stolen_from_related_work():
    """The literature review's Sharpe belongs to another paper, not this one."""
    paper = _paper("We revisit momentum in equity markets.", title="Momentum revisited")
    card = alpha.extract(paper, full_text=_PDF_TEXT)
    assert card is not None
    assert "Sharpe 1.87" in card.effects        # ours, from Results
    assert "Sharpe 0.55" not in card.effects    # theirs, from Related Work


def test_data_sources_still_seen_outside_own_sections():
    """A dataset named anywhere is evidence the paper uses it."""
    paper = _paper("An empirical asset pricing study.")
    card = alpha.extract(
        paper, full_text="Related Work\nPrior studies rely on Compustat.\n"
    )
    assert card is not None and card.data_sources == ["Compustat"]


def test_card_without_full_text_is_marked_abstract_only():
    card = alpha.extract(_paper("Trading returns are predictable."))
    assert card is not None and card.from_full_text is False


def test_own_work_text_strips_others_sections():
    from paperpulse.fulltext import own_work_text

    kept = own_work_text(_PDF_TEXT)
    assert "Sharpe ratio of 1.87" in kept          # ours
    assert "Sharpe ratio of 0.55" not in kept      # related work
    assert "Some Other Author" not in kept         # references
    assert "CRSP" in kept                          # data section survives
    # No headings to act on -> text is returned untouched rather than guessed at.
    assert own_work_text("plain text with no headings") == "plain text with no headings"
    assert own_work_text("") == ""


def test_universe_is_not_polluted_by_the_whole_pdf():
    """Words like 'bond' appear in passing in any finance paper; the abstract
    is what states the paper's actual scope."""
    paper = _paper(
        "We study stablecoin delistings on crypto exchanges.",
        title="Regulation at the gateways",
    )
    body = (
        "Introduction\nWe discuss bond markets, currency carry trades, and the "
        "S&P 500 in passing while reviewing the literature.\n"
    )
    card = alpha.extract(paper, full_text=body)
    assert card is not None
    assert card.universe == ["crypto"]  # not fixed income / FX / US equities


# --- gaps found by running over live arXiv output ---------------------------

def test_basis_points_count_as_an_effect_size():
    """bp is the standard unit for anomaly returns; "48 bp per month" is a
    precise claim and must not read as unquantified."""
    card = alpha.extract(
        _paper(
            "Across long-short anomaly equity portfolios, the median "
            "zero-investment return was 48 bp per month through 2005."
        )
    )
    assert card is not None
    assert "basis points 48" in card.effects
    assert card.universe == ["equities"]   # plain "equity portfolios" counts
    assert card.period == "through 2005"   # one-sided windows are still periods
    assert card.testability == "strong"


def test_defi_does_not_match_the_word_defined():
    """Case-insensitive 'DeFi' without a trailing boundary matched 'define',
    tagging option-pricing theory papers as crypto."""
    card = alpha.extract(
        _paper(
            "Risk-neutral marginals should be defined on the entire support, "
            "with well-defined option prices."
        )
    )
    assert card is not None
    assert "crypto" not in card.universe


def test_one_sided_period_forms():
    for text, expected in [
        ("Stock returns since 1990 were strong.", "since 1990"),
        ("We study equity returns post-2005.", "post 2005"),
        ("Equity data from 2006 onward.", "2006 onward"),
    ]:
        card = alpha.extract(_paper(text))
        assert card is not None and card.period == expected, (text, card.period)
    # A real two-sided range still wins over a one-sided mention.
    card = alpha.extract(_paper("Stock returns from 1990 to 2020, and since 1970."))
    assert card is not None and card.period == "1990-2020"
