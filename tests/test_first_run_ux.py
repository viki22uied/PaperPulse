"""First-run UX + hardening: init presets, API token, PDF allow-list, errors."""

import urllib.error

from paperpulse.cli import TOPIC_PACKS, _friendly_error, build_init_config
from paperpulse.fulltext import _url_allowed


def test_build_init_config_presets():
    for name in TOPIC_PACKS:
        config = build_init_config(name)
        assert config.categories == TOPIC_PACKS[name][0]
        assert config.interests == TOPIC_PACKS[name][1]


def test_build_init_config_overrides_win():
    config = build_init_config("finance", interests="only crypto", categories=["q-fin.TR"])
    assert config.categories == ["q-fin.TR"]
    assert config.interests == "only crypto"
    # No preset, no answers -> library defaults.
    assert build_init_config().categories == ["cs.LG", "cs.CL"]


def test_pdf_url_allowlist():
    assert _url_allowed("https://arxiv.org/pdf/2401.01234v1")
    assert _url_allowed("https://export.arxiv.org/pdf/2401.01234v1")
    assert _url_allowed("https://www.biorxiv.org/content/x.full.pdf")
    assert not _url_allowed("http://arxiv.org/pdf/2401.01234v1")  # plain http
    assert not _url_allowed("https://evil.example.com/steal.pdf")
    assert not _url_allowed("https://notarxiv.org/x.pdf")  # suffix spoof
    assert not _url_allowed("file:///etc/passwd")


def test_friendly_error_mapping():
    rate_limited = urllib.error.HTTPError("u", 429, "Too Many", {}, None)
    assert "rate-limiting" in _friendly_error(rate_limited)
    assert "HTTP 500" in _friendly_error(
        urllib.error.HTTPError("u", 500, "boom", {}, None)
    )
    assert "Network problem" in _friendly_error(urllib.error.URLError("dns down"))
    assert _friendly_error(ValueError("nope")) is None  # unknown -> caller decides


def test_post_requires_token_when_set(monkeypatch, tmp_path):
    """401 without the bearer token, 200 with it."""
    import json
    import threading
    import urllib.request

    from paperpulse.api import make_handler
    from paperpulse.config import Config
    from http.server import ThreadingHTTPServer

    monkeypatch.setenv("PAPERPULSE_API_TOKEN", "s3cret")
    monkeypatch.chdir(tmp_path)  # keep profile state out of the repo
    config = Config(state_path=str(tmp_path / "state.json"), embedding_backend="hashing")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def post(headers):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/feedback",
                data=json.dumps({"like": [], "dislike": []}).encode(),
                headers={"Content-Type": "application/json", **headers},
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status
            except urllib.error.HTTPError as exc:
                return exc.code

        assert post({}) == 401
        assert post({"Authorization": "Bearer wrong"}) == 401
        assert post({"Authorization": "Bearer s3cret"}) == 200
    finally:
        server.shutdown()
        server.server_close()
