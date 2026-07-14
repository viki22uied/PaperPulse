"""Full-text PDF extraction.

Abstracts are enough for ranking, but trust signals and provenance get sharper
with the real thing. We use PyMuPDF when available (fast, good layout) and fall
back to pdfminer.six. Both are optional; if neither is installed we say so
clearly instead of crashing.
"""

from __future__ import annotations

import io
import re
import urllib.request
from dataclasses import dataclass, field

SECTION_HEADS = re.compile(
    r"^\s*(\d+\.?\s+)?(abstract|introduction|related work|background|method\w*|"
    r"approach|experiment\w*|result\w*|evaluation|discussion|limitation\w*|"
    r"conclusion\w*|references)\b",
    re.I | re.M,
)


@dataclass
class ParsedPDF:
    text: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def method_text(self) -> str:
        for key in ("method", "methods", "approach", "methodology"):
            for name, body in self.sections.items():
                if name.lower().startswith(key):
                    return body
        return ""


def _extract_bytes(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text

        return extract_text(io.BytesIO(data))
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "PDF parsing needs PyMuPDF or pdfminer.six "
            "(pip install 'paperpulse[pdf]')."
        ) from exc


def _split_sections(text: str) -> dict[str, str]:
    matches = list(SECTION_HEADS.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = match.group(2).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def parse_bytes(data: bytes) -> ParsedPDF:
    text = _extract_bytes(data)
    return ParsedPDF(text=text, sections=_split_sections(text))


def parse_url(url: str, *, timeout: float = 60.0) -> ParsedPDF:
    request = urllib.request.Request(url, headers={"User-Agent": "PaperPulse/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    return parse_bytes(data)


def parse_path(path: str) -> ParsedPDF:
    with open(path, "rb") as handle:
        return parse_bytes(handle.read())
