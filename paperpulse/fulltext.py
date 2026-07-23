"""Best-effort full-text PDF fetch, for trust signals that look past the
abstract (reproducibility links, dead-link checks). Optional dependency
(``pip install paperpulse[pdf]``); fails soft to ``None`` if it's missing, the
download fails, or the PDF can't be parsed -- callers already treat
``full_text=None`` as "abstract only"."""

from __future__ import annotations

import io
import urllib.request

from .models import Paper


# pdf_url comes from feed XML (semi-trusted); only follow it to hosts the
# supported sources actually serve PDFs from, and only over https.
_ALLOWED_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "nih.gov", "ssrn.com")


def _url_allowed(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS
    )


def fetch_full_text(paper: Paper, *, timeout: float = 20.0, max_bytes: int = 20_000_000) -> str | None:
    if not paper.pdf_url:
        return None
    # Some feeds still hand out http:// links; upgrade rather than reject.
    url = paper.pdf_url.replace("http://", "https://", 1)
    if not _url_allowed(url):
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "PaperPulse/0.1"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes)
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None


__all__ = ["fetch_full_text"]
