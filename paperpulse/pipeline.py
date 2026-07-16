"""Wires the pieces together: ingest -> rank -> trust -> summarise -> render."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
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


@dataclass
class DiffResult:
    """"What changed since last week" for one tracked category set."""

    since: str  # ISO timestamp of the snapshot compared against ("" if none)
    new_papers: list[RankedPaper] = field(default_factory=list)
    # (topic entry, the paper that is fresh evidence for it)
    factor_evidence: list[tuple] = field(default_factory=list)
    # (paper_a, paper_b, note) for pairs whose disagreement reversed direction
    polarity_flips: list[tuple] = field(default_factory=list)

    @property
    def is_first_run(self) -> bool:
        """No prior snapshot: everything is trivially "new", so callers should
        say "no baseline yet" rather than dump the whole batch as changes."""
        return not self.since


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


def _topic_text(entry) -> str:
    """The text a topic entry is embedded as: its name plus aliases.

    Deliberately excludes ``notes`` -- those are free-text lab notes ("tried 6
    variants over 2025, no edge") that describe the *outcome*, not the topic,
    and dilute the vector away from what we're matching against.
    """
    return " ".join([entry.name, *entry.aliases]).strip()


def _literature_reference_texts(topics: list | None) -> list[str]:
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

    # Embed the known-topics log once per run (not per paper) when the opt-in
    # semantic match is enabled -- same "compute once, pass via context" shape
    # as literature_matrix above.
    topic_matrix = None
    if config.known_topics_semantic and backend is not None and topics:
        topic_matrix = backend.encode([_topic_text(t) for t in topics])

    for item in ranked:
        full_text = None
        if config.trust_online:
            from .fulltext import fetch_full_text

            full_text = fetch_full_text(item.paper)

        # Reuse the vector computed during ranking; fall back to encoding only
        # for callers that construct RankedPapers directly (e.g. tests).
        paper_vec = item.vector
        if paper_vec is None and backend is not None:
            paper_vec = backend.encode([item.paper.as_text()])[0]

        literature_crowding = None
        if literature_matrix is not None and paper_vec is not None:
            literature_crowding = float((literature_matrix @ paper_vec).max())

        semantic_topic = None
        semantic_similarity = None
        if topic_matrix is not None and paper_vec is not None and topics:
            sims = topic_matrix @ paper_vec
            best = int(np.argmax(sims))
            if float(sims[best]) >= config.known_topics_semantic_threshold:
                semantic_topic = topics[best]
                semantic_similarity = float(sims[best])

        ctx = trust_mod.SignalContext(
            crowding=item.crowding,
            full_text=full_text,
            topics=topics,
            literature_crowding=literature_crowding,
            semantic_topic=semantic_topic,
            semantic_topic_similarity=semantic_similarity,
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
                venue=item.paper.categories[0] if item.paper.categories else None,
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

    result = DigestResult(markdown=markdown, ranked=ranked, contradictions=contradictions)

    output_path: Path | None = None
    if not dry_run:
        _record_community(config, ranked)
        state.add_snapshot(snapshot_key(config), _make_snapshot(result))
        for item in ranked:
            state.seen_ids.add(item.paper.id)
            state.shown[item.paper.id] = {
                "title": item.paper.title,
                "abstract": item.paper.abstract,
            }
        out_dir = Path(config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{date.today().isoformat()}.md"
        output_path.write_text(markdown, encoding="utf-8")
        state.save(config.state_path)

    result.path = output_path
    return result


def snapshot_key(config: Config) -> str:
    """Snapshots are per category set, so a q-fin digest never diffs against a
    cs.LG one. Sorted so ["a","b"] and ["b","a"] are the same tracked subfield."""
    return ",".join(sorted(config.categories))


def _make_snapshot(result: DigestResult) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "papers": {
            item.paper.id: {
                "title": item.paper.title,
                "score": round(item.score, 4),
                "badge": item.trust.badge if item.trust else "",
                "flags": [s.name for s in item.trust.flags] if item.trust else [],
            }
            for item in result.ranked
        },
        # Keyed a|b so a pair is identity-comparable across runs; the stored
        # polarity is what lets us see the disagreement reverse.
        "contradictions": {
            f"{p.a.id}|{p.b.id}": {"polarity_a": p.polarity_a, "polarity_b": p.polarity_b}
            for p in result.contradictions
        },
    }


def new_factor_evidence(
    config: Config,
    ranked: list[RankedPaper],
    *,
    days: int = 7,
    mark: bool = True,
) -> list[tuple]:
    """Tracked dead/weak factors with fresh matching evidence in ``ranked``.

    "Fresh" means the topic hasn't been matched in the last ``days`` -- the
    ``last_seen_at`` logic behind `paperpulse factors check`, lifted out of the
    CLI so `paperpulse diff` and `GET /api/diff` share it rather than reimplement.

    ``mark`` updates ``last_seen_at``. Callers that must not mutate (the read-only
    API endpoint, where a GET is expected to be safe to repeat) pass False.
    """
    if not config.topics_db:
        return []
    from .topics import TopicLog

    log = TopicLog(config.topics_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found: list[tuple] = []
    try:
        entries = {e.name: e for e in log.all()}
        for item in ranked:
            if item.trust is None:
                continue
            matched = next(
                (s for s in item.trust.signals if s.name == "known_topic" and s.evidence),
                None,
            )
            if matched is None:
                continue
            entry = entries.get(matched.evidence)
            if entry is None or entry.result not in ("dead", "weak"):
                continue
            is_new = not entry.last_seen_at or (
                datetime.fromisoformat(entry.last_seen_at) < cutoff
            )
            if is_new:
                found.append((entry, item))
            if mark:
                log.mark_seen(entry.name)
    finally:
        log.close()
    return found


def diff_digest(config: Config, *, user: str = DEFAULT_USER, mark: bool = False) -> DiffResult:
    """Compare today's batch against the most recent snapshot for this category set.

    Runs with ``skip_seen=False`` on purpose: the normal digest hides papers
    you've already been shown, which would make every survivor look "new" and
    the diff meaningless. We want the true current batch, then diff it against
    what was actually recorded last time.
    """
    result = run_digest(config, user=user, skip_seen=False, dry_run=True)
    state = State.load(config.state_path)
    previous = state.latest_snapshot(snapshot_key(config))

    diff = DiffResult(since=previous["ts"] if previous else "")
    diff.factor_evidence = new_factor_evidence(config, result.ranked, mark=mark)

    if previous is None:
        return diff

    seen_before = set(previous.get("papers", {}))
    diff.new_papers = [i for i in result.ranked if i.paper.id not in seen_before]

    before = previous.get("contradictions", {})
    for pair in result.contradictions:
        prior = before.get(f"{pair.a.id}|{pair.b.id}")
        if prior and prior.get("polarity_a") != pair.polarity_a:
            diff.polarity_flips.append(
                (
                    pair.a,
                    pair.b,
                    f"Disagreement reversed: '{pair.a.title}' went from "
                    f"{'positive' if prior['polarity_a'] > 0 else 'negative'} to "
                    f"{'positive' if pair.polarity_a > 0 else 'negative'}.",
                )
            )
    return diff


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
