"""Network-backed trust signals.

These make outbound HTTP calls, so they are opt-in (``online=True``) and never
run in the default offline assessment. Each fails soft: if the network is
unavailable the signal degrades to OK rather than blocking the digest.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

from ..models import Paper
from . import OK, WARN, FLAG, Signal, signal

URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
_CODE_HOSTS = {"github.com", "gitlab.com", "huggingface.co", "zenodo.org"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects, so a link that passes the host allowlist
    can't be used to bounce the request off-host (redirect-based SSRF)."""

    def redirect_request(self, *args, **kwargs):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)

RETRACTION_WATCH_API = "https://api.labs.crossref.org/data/retractionwatch"
S2_PAPER_API = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"


def _url_ok(url: str, timeout: float = 10.0) -> bool:
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "PaperPulse/0.1"}
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        # Some hosts reject HEAD; retry with a light GET before giving up.
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "PaperPulse/0.1"}
            )
            with _NO_REDIRECT_OPENER.open(request, timeout=timeout) as response:
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
    candidates = [u.rstrip(".,);") for u in URL_RE.findall(haystack)]
    # Exact host match (not prefix/substring) so "github.com.evil.tld" or
    # "github.evil.tld" can't spoof an allowed host and pull an SSRF request
    # out of us.
    urls = [u for u in candidates if urllib.parse.urlparse(u).hostname in _CODE_HOSTS]
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


def _author_key(author: dict) -> str:
    """Stable identity for an author: S2 id if present, else normalised name."""
    if author.get("authorId"):
        return f"id:{author['authorId']}"
    return "name:" + re.sub(r"\W+", " ", (author.get("name") or "").lower()).strip()


def _self_citation_ratio(arxiv_id: str, timeout: float = 15.0) -> tuple[float, int]:
    """Fraction of a paper's references that share an author with it, via
    Semantic Scholar. Returns (ratio, n_references)."""
    aid = arxiv_id.split("v")[0]  # S2 wants the version-less id
    url = S2_PAPER_API.format(aid) + "?fields=authors,references.authors"
    headers = {"User-Agent": "PaperPulse/0.1"}
    if os.environ.get("S2_API_KEY"):
        headers["x-api-key"] = os.environ["S2_API_KEY"]
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    own = {_author_key(a) for a in data.get("authors") or []}
    refs = [r for r in (data.get("references") or []) if r.get("authors")]
    if not own or not refs:
        return 0.0, len(refs)
    shared = sum(
        1 for r in refs if own & {_author_key(a) for a in r["authors"]}
    )
    return shared / len(refs), len(refs)


@signal("self_citation")
def self_citation_signal(paper: Paper, *, online: bool = False, **_) -> Signal:
    """Flag papers whose reference list leans heavily on the same authors --
    a common way to inflate apparent impact."""
    if not online:
        return Signal("self_citation", OK, "Self-citation check skipped (offline).")
    try:
        ratio, n_refs = _self_citation_ratio(paper.id)
    except Exception:
        return Signal("self_citation", OK, "Self-citation check unavailable.")
    if n_refs < 5:
        return Signal("self_citation", OK, "Too few references to judge.")
    if ratio >= 0.4:
        return Signal(
            "self_citation",
            WARN,
            f"{ratio:.0%} of references share an author with this paper -- "
            "impact may be self-reinforced.",
            evidence=f"{ratio:.0%} of {n_refs} references",
            confidence=0.7,
        )
    return Signal(
        "self_citation", OK, f"Self-citation looks normal ({ratio:.0%}).",
        evidence=f"{ratio:.0%} of {n_refs} references",
    )
