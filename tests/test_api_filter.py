"""Filter-bar plumbing: category validation, wildcard expansion, cache keying."""

from paperpulse import api
from paperpulse.config import Config


def test_parse_cats_keeps_only_known_categories():
    assert api._parse_cats("cats=q-fin.TR,econ.GN") == ["q-fin.TR", "econ.GN"]
    assert api._parse_cats("cats=q-fin.TR,bogus.XX") == ["q-fin.TR"]
    assert api._parse_cats("cats=") is None  # empty -> fall back to config
    assert api._parse_cats("") is None


def test_initial_selection_expands_wildcards():
    sel = api._initial_selection(Config(categories=["q-fin.*", "econ.*"]))
    assert "q-fin.ST" in sel and "econ.EM" in sel
    assert all(c.startswith(("q-fin.", "econ.")) for c in sel)
    # Exact categories pass through; unknown ones are dropped.
    assert api._initial_selection(Config(categories=["cs.LG", "nope.ZZ"])) == ["cs.LG"]


def test_cached_digest_keys_by_category_set(monkeypatch):
    api._digest_cache.clear()
    calls = []
    monkeypatch.setattr(api, "run_digest", lambda cfg, **_: calls.append(tuple(cfg.categories)) or "R")

    api._cached_digest(Config(categories=["q-fin.TR"]))
    api._cached_digest(Config(categories=["q-fin.TR"]))  # cached, no refetch
    api._cached_digest(Config(categories=["econ.GN"]))    # different key, refetch
    assert calls == [("q-fin.TR",), ("econ.GN",)]
