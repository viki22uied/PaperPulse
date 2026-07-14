"""The interest profile: what "relevant to me" means, as a vector.

A profile starts from a short paragraph describing your interests (and,
optionally, a handful of papers you already like). Feedback then nudges the
vector using Rocchio's rule -- pull toward papers you mark useful, push away
from the ones you don't -- so relevance sharpens the more you use it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .embeddings import EmbeddingBackend


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


@dataclass
class InterestProfile:
    """A learnable representation of a user's interests.

    ``vector`` is the current interest centroid. ``seed_vector`` is the
    embedding of the original description; we keep it so feedback can never
    drift infinitely far from the interests you actually wrote down.
    """

    description: str
    vector: np.ndarray
    seed_vector: np.ndarray
    n_feedback: int = 0
    liked_ids: list[str] = field(default_factory=list)
    disliked_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_text(
        cls,
        description: str,
        backend: EmbeddingBackend,
        seed_papers: list[str] | None = None,
    ) -> "InterestProfile":
        texts = [description] + list(seed_papers or [])
        vectors = backend.encode(texts)
        centroid = _unit(vectors.mean(axis=0))
        seed = _unit(vectors[0])
        return cls(description=description, vector=centroid, seed_vector=seed)

    def update(
        self,
        liked: np.ndarray | None = None,
        disliked: np.ndarray | None = None,
        *,
        alpha: float = 1.0,
        beta: float = 0.8,
        gamma: float = 0.3,
        anchor: float = 0.15,
    ) -> None:
        """Rocchio update.

        ``alpha`` weights the current vector, ``beta`` the liked centroid,
        ``gamma`` the disliked centroid, and ``anchor`` keeps a little pull
        toward the original seed so the profile stays grounded.
        """
        updated = alpha * self.vector + anchor * self.seed_vector
        if liked is not None and len(liked):
            updated = updated + beta * _unit(np.asarray(liked).mean(axis=0))
            self.n_feedback += len(liked)
        if disliked is not None and len(disliked):
            updated = updated - gamma * _unit(np.asarray(disliked).mean(axis=0))
            self.n_feedback += len(disliked)
        self.vector = _unit(updated)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "vector": self.vector.astype(float).tolist(),
            "seed_vector": self.seed_vector.astype(float).tolist(),
            "n_feedback": self.n_feedback,
            "liked_ids": self.liked_ids,
            "disliked_ids": self.disliked_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterestProfile":
        return cls(
            description=data["description"],
            vector=np.asarray(data["vector"], dtype=np.float32),
            seed_vector=np.asarray(
                data.get("seed_vector", data["vector"]), dtype=np.float32
            ),
            n_feedback=int(data.get("n_feedback", 0)),
            liked_ids=list(data.get("liked_ids", [])),
            disliked_ids=list(data.get("disliked_ids", [])),
        )
