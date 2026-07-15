"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("paperpulse.yaml")


@dataclass
class Config:
    # What to pull
    source: str = "arxiv"  # arxiv | biorxiv | pubmed
    categories: list[str] = field(default_factory=lambda: ["cs.LG", "cs.CL"])
    keywords: list[str] = field(default_factory=list)
    interests: str = (
        "Machine learning methods for natural language processing, with an "
        "interest in retrieval, embeddings, and practical model evaluation."
    )
    seed_papers: list[str] = field(default_factory=list)
    # Topics to actively rank *down* (e.g. factors you've already worked
    # extensively on), independent of the learned Rocchio profile -- applies
    # even on a cold-start profile with zero feedback yet.
    avoid_topics: list[str] = field(default_factory=list)
    avoid_weight: float = 0.5

    # Ingestion
    max_results: int = 200

    # Ranking
    top_n: int = 5
    diversity: float = 0.3
    min_score: float = 0.0
    embedding_backend: str = "auto"  # auto | hashing | sentence-transformers

    # Trust signals
    trust: bool = True
    trust_signals: list[str] | None = None  # None => library defaults
    trust_online: bool = False  # enable network checks (links, retractions)

    # Region tagging (B1/B2)
    region_filter: list[str] = field(default_factory=list)  # [] => no filter
    region_filter_include_unspecified: bool = True
    # factor/topic name (matches the topics log) -> regions already tested,
    # e.g. {"board diversity": ["USA"]}. A paper on that factor in a region
    # NOT listed here gets a green "untested region" note.
    already_tested_regions: dict[str, list[str]] = field(default_factory=dict)

    # Contradiction mapping
    contradictions: bool = True

    # Summarisation
    use_llm: bool = False
    summary_sentences: int = 3

    # Output / state
    output_dir: str = "digests"
    state_path: str = ".paperpulse_state.json"
    community_db: str = ""  # path to shared SQLite trust store, "" = disabled
    topics_db: str = ""  # path to known/already-tried topics log, "" = disabled

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text()) or {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        path.write_text(yaml.safe_dump(asdict(self), sort_keys=False))
        return path
