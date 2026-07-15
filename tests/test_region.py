"""Region auto-tagging (B1) and cross-region transfer note (B2)."""

from paperpulse.config import Config
from paperpulse.digest import render_markdown
from paperpulse.models import Paper, RankedPaper
from paperpulse.pipeline import _attach_regions, _filter_regions
from paperpulse.region import UNSPECIFIED, detect_regions
from paperpulse.trust import FLAG, Signal, TrustReport


def test_detect_regions_usa():
    assert detect_regions("We study S&P 500 constituents and NYSE-listed firms.") == ["USA"]


def test_detect_regions_china():
    assert detect_regions("An event study of CSI 300 and Shanghai-listed A-shares.") == ["CHN"]


def test_detect_regions_unspecified():
    assert detect_regions("A general asset-pricing model with no named market.") == [UNSPECIFIED]


def _ranked_with_known_topic(title, abstract, matched_name):
    paper = Paper(id="1", title=title, abstract=abstract)
    report = TrustReport(
        signals=[Signal("known_topic", FLAG, "already logged", evidence=matched_name)],
        score=0.5,
    )
    return RankedPaper(paper=paper, score=0.8, trust=report)


def test_region_note_flags_untested_region():
    item = _ranked_with_known_topic(
        "Board diversity in Indian firms",
        "We study board gender diversity and stock returns for NSE-listed firms.",
        "board diversity",
    )
    config = Config(already_tested_regions={"board diversity": ["USA"]})
    _attach_regions(config, [item])
    assert item.regions == ["IND"]
    assert "Untested region" in item.region_note


def test_region_note_absent_when_already_tested():
    item = _ranked_with_known_topic(
        "Board diversity in US firms",
        "We study board gender diversity and stock returns for S&P 500 firms.",
        "board diversity",
    )
    config = Config(already_tested_regions={"board diversity": ["USA"]})
    _attach_regions(config, [item])
    assert item.region_note == ""


def test_region_filter_keeps_matching_and_unspecified():
    usa = RankedPaper(paper=Paper(id="a", title="t", abstract="S&P 500 study"), score=0.5)
    chn = RankedPaper(paper=Paper(id="b", title="t", abstract="CSI 300 study"), score=0.5)
    unspecified = RankedPaper(paper=Paper(id="c", title="t", abstract="asset pricing"), score=0.5)
    config = Config(region_filter=["USA"])
    _attach_regions(config, [usa, chn, unspecified])
    kept = {item.paper.id for item in _filter_regions(config, [usa, chn, unspecified])}
    assert kept == {"a", "c"}


def test_digest_renders_region_and_note():
    item = _ranked_with_known_topic(
        "Board diversity in Indian firms",
        "We study board gender diversity for NSE-listed firms.",
        "board diversity",
    )
    item.regions = ["IND"]
    item.region_note = "Untested region (IND) for 'board diversity' -- may still be valid to explore."
    markdown = render_markdown([item])
    assert "Region: IND" in markdown
    assert "Untested region" in markdown
