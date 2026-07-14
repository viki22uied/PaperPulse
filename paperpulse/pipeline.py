"""Wires the pieces together: ingest -> rank -> trust -> summarise -> render."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from . import trust as trust_mod
from .config import Config
from .contradiction import ContradictionPair, contradiction_map
from .digest import render_markdown
from .embeddings import build_backend
from .models import Paper, RankedPaper
from .profile import InterestProfile
from .rank import rank_papers
from .sources import Query, get_source
from .store import DEFAULT_USER, State
from .summarize import summarise


@dataclass
class DigestResult:
    markdown: str
    ranked: list[RankedPaper]
    contradictions: list[ContradictionPair]
    path: Path | None = None


def _load_backend(config: Config):
    return build_backend(config.embedding_backend)


def ensure_profile(
    config: Config, state: State, backend, user: str = DEFAULT_USER
) -> InterestProfile:
    """Return the stored profile for ``user``, (re)building it from config if it
    is missing or the interest description has changed."""
    profile = state.get_profile(user)
    if profile is None or profile.description != config.interests:
        profile = InterestProfile.from_text(
            config.interests, backend, seed_papers=config.seed_papers
        )
        state.set_profile(profile, user)
    return profile


def _fetch(config: Config) -> list[Paper]:
    source = get_source(config.source)
    query = Query(
        categories=config.categories,
        keywords=config.keywords,
        max_results=config.max_results,
    )
    return source.fetch(query)


def _attach_trust(config: Config, ranked: list[RankedPaper]) -> None:
    if not config.trust:
        return
    context_base = dict(online=config.trust_online)
    signals = config.trust_signals  # None -> library defaults
    if config.trust_online and signals is None:
        signals = trust_mod.DEFAULT_SIGNALS + [
            "link_check", "retraction", "self_citation",
        ]
    for item in ranked:
        ctx = trust_mod.SignalContext(crowding=item.crowding, **context_base)
        item.trust = trust_mod.assess(item.paper, enabled=signals, context=ctx)


def _record_community(config: Config, ranked: list[RankedPaper]) -> None:
    if not config.community_db:
        return
    from .community import CommunityDB

    db = CommunityDB(config.community_db)
    try:
        for item in ranked:
            if item.trust is None:
                continue
            db.record_trust(
                item.paper.id,
                score=item.trust.score,
                badge=item.trust.badge,
                flags=[s.name for s in item.trust.flags],
                venue=(item.paper.categories or [None])[0],
                authors=item.paper.authors,
            )
    finally:
        db.close()


def run_digest(
    config: Config,
    *,
    user: str = DEFAULT_USER,
    skip_seen: bool = True,
    dry_run: bool = False,
) -> DigestResult:
    """Generate today's digest end to end."""
    backend = _load_backend(config)
    state = State.load(config.state_path)
    profile = ensure_profile(config, state, backend, user)

    papers = _fetch(config)
    if skip_seen:
        papers = [p for p in papers if p.id not in state.seen_ids]

    ranked = rank_papers(
        papers,
        profile,
        backend,
        top_n=config.top_n,
        diversity=config.diversity,
        min_score=config.min_score,
    )

    _attach_trust(config, ranked)

    for item in ranked:
        item.summary = summarise(
            item.paper,
            use_llm=config.use_llm,
            max_sentences=config.summary_sentences,
        )

    contradictions: list[ContradictionPair] = []
    if config.contradictions:
        contradictions = contradiction_map(papers, backend)

    subtitle = f"{config.source} · " + " · ".join(config.categories)
    markdown = render_markdown(ranked, subtitle=subtitle)

    output_path: Path | None = None
    if not dry_run:
        _record_community(config, ranked)
        for item in ranked:
            state.seen_ids.add(item.paper.id)
            state.shown[item.paper.id] = {
                "title": item.paper.title,
                "abstract": item.paper.abstract,
            }
        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{date.today().isoformat()}.md"
        output_path.write_text(markdown)
        state.save(config.state_path)

    return DigestResult(
        markdown=markdown,
        ranked=ranked,
        contradictions=contradictions,
        path=output_path,
    )


def apply_feedback(
    config: Config,
    liked_ids: list[str],
    disliked_ids: list[str],
    *,
    user: str = DEFAULT_USER,
) -> InterestProfile:
    """Update the stored interest profile from thumbs-up / thumbs-down ids."""
    backend = _load_backend(config)
    state = State.load(config.state_path)
    profile = ensure_profile(config, state, backend, user)

    def embed(ids: list[str]) -> np.ndarray | None:
        texts = []
        for pid in ids:
            record = state.shown.get(pid)
            if record:
                texts.append(
                    Paper(
                        id=pid,
                        title=record["title"],
                        abstract=record["abstract"],
                    ).as_text()
                )
        return backend.encode(texts) if texts else None

    profile.update(embed(liked_ids), embed(disliked_ids))
    profile.liked_ids.extend(liked_ids)
    profile.disliked_ids.extend(disliked_ids)

    state.set_profile(profile, user)
    state.save(config.state_path)
    return profile


def find_similar_to_work(
    config: Config, work_path: str, *, top_n: int = 10
):
    """Cross-reference a code file / notebook against the latest papers."""
    from .crossref import load_work, similar_papers

    backend = _load_backend(config)
    papers = _fetch(config)
    work_text = load_work(work_path)
    return similar_papers(work_text, papers, backend, top_n=top_n)
