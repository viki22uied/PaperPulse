"""Embedding backends.

The whole point of PaperPulse is ranking, and ranking needs vectors that live
in a *stable* space so a profile learned today still makes sense tomorrow. Two
backends satisfy that:

* ``HashingBackend`` (default) -- a hashed bag-of-n-grams. Fixed dimensions,
  deterministic, no training and no model download. Good enough to separate
  "about my topic" from "not about my topic", and it runs anywhere.
* ``SentenceTransformerBackend`` (optional) -- real semantic embeddings for
  noticeably better relevance. Enabled when ``sentence-transformers`` is
  installed.

Both return L2-normalised float32 arrays, so a dot product is the cosine
similarity.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


def _l2_normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class EmbeddingBackend(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an ``(len(texts), dim)`` array of unit vectors."""


class HashingBackend:
    """Dependency-light embeddings via scikit-learn's HashingVectorizer.

    Stateless and stable: the same text always maps to the same vector, which
    is what lets a stored interest profile stay comparable across runs.
    """

    def __init__(self, dim: int = 2 ** 14, ngram_range: tuple[int, int] = (1, 2)):
        from sklearn.feature_extraction.text import HashingVectorizer

        self.dim = dim
        self._vectorizer = HashingVectorizer(
            n_features=dim,
            ngram_range=ngram_range,
            alternate_sign=False,  # keep components non-negative for cosine
            norm=None,
            stop_words="english",
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        sparse = self._vectorizer.transform(texts)
        return _l2_normalise(sparse.toarray().astype(np.float32))


class SentenceTransformerBackend:
    """Semantic embeddings via sentence-transformers (optional dependency)."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self._model.encode(
            texts, convert_to_numpy=True, show_progress_bar=False
        )
        return _l2_normalise(vectors.astype(np.float32))


def build_backend(name: str = "auto", **kwargs) -> EmbeddingBackend:
    """Construct an embedding backend by name.

    ``auto`` prefers sentence-transformers when it is importable and quietly
    falls back to the hashing backend otherwise.
    """
    name = (name or "auto").lower()

    if name in {"hashing", "hash"}:
        return HashingBackend(**kwargs)
    if name in {"sentence-transformers", "st", "transformer"}:
        return SentenceTransformerBackend(**kwargs)
    if name == "auto":
        try:
            return SentenceTransformerBackend()
        except Exception:
            return HashingBackend()
    raise ValueError(f"unknown embedding backend: {name!r}")
