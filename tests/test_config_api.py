"""GET/POST /api/config -- the browser-side equivalent of `paperpulse init`."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import yaml

from paperpulse.api import TOPIC_PACKS, make_handler
from paperpulse.config import Config


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "paperpulse.yaml"
    config = Config(
        state_path=str(tmp_path / "state.json"),
        embedding_backend="hashing",
        trust_online=False,
        max_results=1,
        top_n=1,
    )
    config.save(config_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config, str(config_path)))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", config_path
    finally:
        server.shutdown()
        server.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, json.loads(response.read())


def _post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_get_config_returns_current_settings_and_packs(live_server):
    base, _ = live_server
    status, body = _get(f"{base}/api/config")
    assert status == 200
    assert body["categories"] == ["cs.LG", "cs.CL"]  # Config() default
    assert set(body["packs"]) == set(TOPIC_PACKS)
    assert body["packs"]["finance"]["categories"] == TOPIC_PACKS["finance"][0]


def test_post_config_with_preset_updates_categories_and_interests(live_server):
    base, config_path = live_server
    status, body = _post(f"{base}/api/config", {"preset": "finance"})
    assert status == 200
    assert body["categories"] == TOPIC_PACKS["finance"][0]
    assert body["interests"] == TOPIC_PACKS["finance"][1]

    # Persisted to disk, and the next GET reflects it.
    on_disk = yaml.safe_load(config_path.read_text())
    assert on_disk["categories"] == TOPIC_PACKS["finance"][0]
    _, refetched = _get(f"{base}/api/config")
    assert refetched["categories"] == TOPIC_PACKS["finance"][0]


def test_post_config_preserves_other_settings(live_server):
    """Updating categories/interests must not reset trust/max_results/etc back
    to library defaults -- only the two fields being edited should change."""
    base, config_path = live_server
    _post(f"{base}/api/config", {"preset": "econ"})
    on_disk = yaml.safe_load(config_path.read_text())
    assert on_disk["max_results"] == 1  # set in the fixture, must survive
    assert on_disk["top_n"] == 1


def test_post_config_custom_interests_without_preset(live_server):
    base, _ = live_server
    status, body = _post(f"{base}/api/config", {"interests": "only crypto derivatives"})
    assert status == 200
    assert body["interests"] == "only crypto derivatives"
    assert body["categories"] == ["cs.LG", "cs.CL"]  # untouched, no preset given


def test_post_config_rejects_unknown_preset(live_server):
    base, _ = live_server
    status, body = _post(f"{base}/api/config", {"preset": "not-a-real-pack"})
    assert status == 400
    assert "error" in body


def test_post_config_rejects_empty_body(live_server):
    base, _ = live_server
    status, body = _post(f"{base}/api/config", {})
    assert status == 400
