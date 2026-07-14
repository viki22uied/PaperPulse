"""Slack / Discord delivery via incoming webhooks.

Pass the webhook URL explicitly or via ``PAPERPULSE_SLACK_WEBHOOK`` /
``PAPERPULSE_DISCORD_WEBHOOK``. Both accept a simple ``{"text": ...}`` payload,
so we keep the formatting to trimmed markdown that renders acceptably in each.
"""

from __future__ import annotations

import json
import os
import urllib.request

_MAX = 3500  # keep well under both platforms' message limits


def _post(url: str, payload: dict, timeout: float = 15.0) -> None:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "PaperPulse/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not (200 <= response.status < 300):
            raise RuntimeError(f"webhook returned HTTP {response.status}")


def send_slack(markdown: str, *, webhook: str | None = None) -> None:
    webhook = webhook or os.getenv("PAPERPULSE_SLACK_WEBHOOK")
    if not webhook:
        raise RuntimeError("set PAPERPULSE_SLACK_WEBHOOK or pass webhook=...")
    _post(webhook, {"text": markdown[:_MAX]})


def send_discord(markdown: str, *, webhook: str | None = None) -> None:
    webhook = webhook or os.getenv("PAPERPULSE_DISCORD_WEBHOOK")
    if not webhook:
        raise RuntimeError("set PAPERPULSE_DISCORD_WEBHOOK or pass webhook=...")
    _post(webhook, {"content": markdown[:_MAX]})
