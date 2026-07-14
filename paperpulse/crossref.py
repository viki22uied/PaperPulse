"""Cross-reference your own work against papers.

Paste a code file or notebook; PaperPulse embeds it and finds papers whose
method text is functionally closest. Useful for "has someone already published
what I'm building?" and for spotting prior art before you reinvent it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .embeddings import EmbeddingBackend
from .models import Paper

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
_COMMENT = re.compile(r"#.*|//.*|/\*.*?\*/|\"\"\".*?\"\"\"|'''.*?'''", re.S)


def _split_identifier(name: str) -> list[str]:
    # snake_case and camelCase -> words, so "cosine_similarity" and
    # "cosineSimilarity" both surface the same terms for embedding.
    parts = re.split(r"_+", name)
    words: list[str] = []
    for part in parts:
        words.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", part) or [part])
    return [w.lower() for w in words if w]


def code_to_text(source: str) -> str:
    """Turn source code into a bag of meaningful words: comments/docstrings kept
    verbatim, identifiers split into their component words."""
    comments = " ".join(m.group(0) for m in _COMMENT.finditer(source))
    stripped = _COMMENT.sub(" ", source)
    words: list[str] = []
    for token in _IDENTIFIER.findall(stripped):
        words.extend(_split_identifier(token))
    clean_comments = re.sub(r"[#/*'\"]", " ", comments)
    return f"{clean_comments} {' '.join(words)}".strip()


def notebook_to_text(path: str | Path) -> str:
    data = json.loads(Path(path).read_text())
    chunks: list[str] = []
    for cell in data.get("cells", []):
        src = "".join(cell.get("source", []))
        if cell.get("cell_type") == "markdown":
            chunks.append(src)
        else:
            chunks.append(code_to_text(src))
    return "\n".join(chunks)


def load_work(path: str | Path) -> str:
    path = Path(path)
    if path.suffix == ".ipynb":
        return notebook_to_text(path)
    return code_to_text(path.read_text())


@dataclass
class Similarity:
    paper: Paper
    score: float


def similar_papers(
    work_text: str,
    papers: list[Paper],
    backend: EmbeddingBackend,
    *,
    top_n: int = 10,
) -> list[Similarity]:
    """Rank ``papers`` by method-level similarity to the given work."""
    if not papers:
        return []
    query = backend.encode([work_text])[0]
    matrix = backend.encode([p.as_text() for p in papers])
    scores = matrix @ query
    order = scores.argsort()[::-1][:top_n]
    return [Similarity(paper=papers[i], score=float(scores[i])) for i in order]
