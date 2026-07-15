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


def _literature_reference_texts(topics: list) -> list[str]:
    from .literature import CANONICAL_FACTOR_PAPERS

    topic_texts = [
        " ".join([t.name, *t.aliases, t.notes]).strip() for t in (topics or [])
    ]
    return CANONICAL_FACTOR_PAPERS + [t for t in topic_texts if t]


def _attach_trust(config: Config, ranked: list[RankedPaper], backend=None) -> None:
    if not config.trust:
        return
    context_base = dict(online=config.trust_online)
    signals = config.trust_signals  # None -> library defaults
    if config.trust_online and signals is None:
        signals = trust_mod.DEFAULT_SIGNALS + [
            "link_check", "retraction", "self_citation", "related_work",
        ]

    topics = None
    if config.topics_db:
        from .topics import TopicLog

        log = TopicLog(config.topics_db)
        try:
            topics = log.all()
        finally:
            log.close()

    literature_matrix = None
    if backend is not None:
        reference_texts = _literature_reference_texts(topics)
        if reference_texts:
            literature_matrix = backend.encode(reference_texts)

    for item in ranked:
        full_text = None
        if config.trust_online:
            from .fulltext import fetch_full_text

            full_text = fetch_full_text(item.paper)

        literature_crowding = None
        if literature_matrix is not None and backend is not None:
            paper_vec = backend.encode([item.paper.as_text()])[0]
            literature_crowding = float((literature_matrix @ paper_vec).max())

        ctx = trust_mod.SignalContext(
            crowding=item.crowding,
            full_text=full_text,
            topics=topics,
            literature_crowding=literature_crowding,
            **context_base,
        )
        item.trust = trust_mod.assess(item.paper, enabled=signals, context=ctx)


def _attach_regions(config: Config, ranked: list[RankedPaper]) -> None:
    """Tag each paper with detected market/region(s) (B1), and note when a
    paper's region isn't one already logged as tested for a matched
    known/tried topic (B2)."""
    from .region import UNSPECIFIED, detect_regions

    for item in ranked:
        item.regions = detect_regions(f"{item.paper.title} {item.paper.abstract}")
        if not config.already_tested_regions or item.trust is None:
            continue
        matched_name = next(
            (s.evidence for s in item.trust.signals if s.name == "known_topic" and s.evidence),
            None,
        )
        if not matched_name:
            continue
        tested = set(config.already_tested_regions.get(matched_name, []))
        detected = set(item.regions) - {UNSPECIFIED}
        if detected and not detected & tested:
            item.region_note = (
                f"Untested region ({', '.join(sorted(detected))}) for "
                f"'{matched_name}' -- may still be valid to explore."
            )


def _filter_regions(config: Config, ranked: list[RankedPaper]) -> list[RankedPaper]:
    if not config.region_filter:
        return ranked
    wanted = set(config.region_filter)
    from .region import UNSPECIFIED

    def keep(item: RankedPaper) -> bool:
        regions = set(item.regions)
        if regions & wanted:
            return True
        return config.region_filter_include_unspecified and UNSPECIFIED in regions

    return [item for item in ranked if keep(item)]


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

    avoid_vector = None
    if config.avoid_topics:
        avoid_matrix = backend.encode(list(config.avoid_topics))
        avoid_vector = avoid_matrix.mean(axis=0)
        norm = float(np.linalg.norm(avoid_vector))
        if norm:
            avoid_vector = avoid_vector / norm

    ranked = rank_papers(
        papers,
        profile,
        backend,
        top_n=config.top_n,
        diversity=config.diversity,
        min_score=config.min_score,
        avoid_vector=avoid_vector,
        avoid_weight=config.avoid_weight,
    )

    _attach_trust(config, ranked, backend=backend)
    _attach_regions(config, ranked)
    ranked = _filter_regions(config, ranked)

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


# Maps a `feedback --reason` to what gets logged in the shared topics table.
# "irrelevant" doesn't imply anything about the topic itself, so it logs nothing.
_DISLIKE_REASON_RESULT = {"crowded": "weak", "weak-result": "weak", "already-tried": "dead"}


def _log_dislike_reason(config: Config, state: State, disliked_ids: list[str], reason: str | None) -> None:
    result = _DISLIKE_REASON_RESULT.get(reason or "")
    if not result or not config.topics_db:
        return
    from .topics import TopicLog

    log = TopicLog(config.topics_db)
    try:
        for pid in disliked_ids:
            record = state.shown.get(pid)
            if not record:
                continue
            log.add(
                record["title"],
                source="manual",
                result=result,
                notes=f"via feedback --reason {reason}",
            )
    finally:
        log.close()


def apply_feedback(
    config: Config,
    liked_ids: list[str],
    disliked_ids: list[str],
    *,
    user: str = DEFAULT_USER,
    reason: str | None = None,
) -> InterestProfile:
    """Update the stored interest profile from thumbs-up / thumbs-down ids.

    ``reason`` (on dislikes) optionally routes into the shared known/tried
    topics log -- see ``_DISLIKE_REASON_RESULT`` -- so a dislike becomes an
    explicit, growing record instead of just nudging the embedding vector."""
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
    _log_dislike_reason(config, state, disliked_ids, reason)

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
