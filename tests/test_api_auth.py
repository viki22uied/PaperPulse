"""PAPERPULSE_API_TOKEN must gate GET as well as POST -- it used to only
check POST, so setting the token to lock down a shared-server instance still
left every read (digest, notes, config, score-accuracy) wide open.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from paperpulse.api import make_handler
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
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _get(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response
    except urllib.error.HTTPError as exc:
        return exc.code, exc


def test_get_config_open_when_no_token_set(live_server):
    status, _ = _get(f"{live_server}/api/config")
    assert status == 200


def test_get_config_requires_token_when_set(live_server, monkeypatch):
    monkeypatch.setenv("PAPERPULSE_API_TOKEN", "secret123")

    status, resp = _get(f"{live_server}/api/config")
    assert status == 401
    assert json.loads(resp.read())["error"] == "unauthorized"

    status, resp = _get(f"{live_server}/api/config", token="wrong")
    assert status == 401

    status, resp = _get(f"{live_server}/api/config", token="secret123")
    assert status == 200


def test_root_shell_is_exempt_from_the_token(live_server, monkeypatch):
    """The static HTML shell has no server-rendered secrets -- it's the
    /api/* routes it calls client-side that must be gated."""
    monkeypatch.setenv("PAPERPULSE_API_TOKEN", "secret123")
    status, _ = _get(f"{live_server}/")
    assert status == 200


def test_post_still_requires_token_when_set(live_server, monkeypatch):
    monkeypatch.setenv("PAPERPULSE_API_TOKEN", "secret123")
    request = urllib.request.Request(
        f"{live_server}/api/config",
        data=json.dumps({"interests": "x"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=10)
        assert False, "expected 401"
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
