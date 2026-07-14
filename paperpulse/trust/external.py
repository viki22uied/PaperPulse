"""Network-backed trust signals.

These make outbound HTTP calls, so they are opt-in (``online=True``) and never
run in the default offline assessment. Each fails soft: if the network is
unavailable the signal degrades to OK rather than blocking the digest.
"""

from __future__ import annotations

import re
import urllib.request

from ..models import Paper
from . import OK, WARN, FLAG, Signal, signal

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
CODE_HOST_RE = re.compile(r"https?://(github\.com|gitlab\.com|huggingface\.co|zenodo\.org)/\S+", re.I)

RETRACTION_WATCH_API = "https://api.labs.crossref.org/data/retractionwatch"


def _url_ok(url: str, timeout: float = 10.0) -> bool:
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "PaperPulse/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        # Some hosts reject HEAD; retry with a light GET before giving up.
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "PaperPulse/0.1"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return 200 <= response.status < 400
        except Exception:
            return False


@signal("link_check")
def link_check_signal(
    paper: Paper, *, online: bool = False, full_text: str | None = None, **_
) -> Signal:
    """Detect dead code/data links referenced by the paper."""
    if not online:
        return Signal("link_check", OK, "Link check skipped (offline).")
    haystack = paper.abstract + (full_text or "")
    urls = [u.rstrip(".,);") for u in CODE_HOST_RE.findall(haystack)]
    # CODE_HOST_RE captures only the host group; re-extract full URLs.
    urls = [m.rstrip(".,);") for m in URL_RE.findall(haystack)
            if re.match(r"https?://(github|gitlab|huggingface|zenodo)", m, re.I)]
    if not urls:
        return Signal("link_check", OK, "No code/data links to verify.")
    dead = [u for u in urls if not _url_ok(u)]
    if dead:
        return Signal(
            "link_check",
            FLAG,
            f"{len(dead)} of {len(urls)} code/data link(s) look unreachable: "
            f"{dead[0]}",
        )
    return Signal("link_check", OK, f"All {len(urls)} code/data link(s) resolve.")


def _query_retraction(title: str, timeout: float = 15.0) -> bool:
    """Best-effort check against the Retraction Watch dataset (served via
    Crossref Labs). Returns True if a plausible retraction match is found."""
    import json
    import urllib.parse

    query = urllib.parse.urlencode({"query": title[:120], "rows": 5})
    request = urllib.request.Request(
        f"{RETRACTION_WATCH_API}?{query}",
        headers={"User-Agent": "PaperPulse/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    items = data.get("message", {}).get("items", data if isinstance(data, list) else [])
    needle = re.sub(r"\W+", " ", title.lower()).strip()
    for item in items or []:
        cand = str(item.get("title", "")).lower()
        if needle and needle[:40] in re.sub(r"\W+", " ", cand):
            return True
    return False


@signal("retraction")
def retraction_signal(paper: Paper, *, online: bool = False, **_) -> Signal:
    """Cross-check the title against the Retraction Watch database."""
    if not online:
        return Signal("retraction", OK, "Retraction check skipped (offline).")
    try:
        if _query_retraction(paper.title):
            return Signal(
                "retraction",
                FLAG,
                "Possible match in the Retraction Watch database -- verify before "
                "citing.",
            )
    except Exception:
        return Signal("retraction", OK, "Retraction check unavailable.")
    return Signal("retraction", OK, "No retraction match found.")
