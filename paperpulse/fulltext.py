"""Best-effort full-text PDF fetch, for trust signals that look past the
abstract (reproducibility links, dead-link checks). Optional dependency
(``pip install paperpulse[pdf]``); fails soft to ``None`` if it's missing, the
download fails, or the PDF can't be parsed -- callers already treat
``full_text=None`` as "abstract only"."""

from __future__ import annotations

import io
import urllib.request

from .models import Paper


def fetch_full_text(paper: Paper, *, timeout: float = 20.0, max_bytes: int = 20_000_000) -> str | None:
    if not paper.pdf_url:
        return None
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        request = urllib.request.Request(
            paper.pdf_url, headers={"User-Agent": "PaperPulse/0.1"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes)
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return None


__all__ = ["fetch_full_text"]
