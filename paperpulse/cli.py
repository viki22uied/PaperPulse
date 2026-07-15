"""Command-line interface."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .config import Config, DEFAULT_CONFIG_PATH
from .pipeline import apply_feedback, find_similar_to_work, run_digest


def _cmd_init(args: argparse.Namespace) -> int:
    if DEFAULT_CONFIG_PATH.exists() and not args.force:
        print(f"{DEFAULT_CONFIG_PATH} already exists (use --force to overwrite).")
        return 1
    config = Config()
    if args.seed_avoid:
        text = Path(args.seed_avoid).read_text()
        topics = [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]
        config.avoid_topics = topics
    path = config.save()
    print(
        f"Wrote starter config to {path}. Edit `interests`, `categories`, and "
        f"`source`, then run `paperpulse run`."
    )
    if args.seed_avoid:
        print(f"Seeded {len(config.avoid_topics)} avoid_topics from {args.seed_avoid}.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    if args.top_n:
        config.top_n = args.top_n
    if args.categories:
        config.categories = args.categories
    if args.source:
        config.source = args.source
    if args.llm:
        config.use_llm = True
    if args.online:
        config.trust_online = True

    result = run_digest(
        config,
        user=args.user,
        skip_seen=not args.include_seen,
        dry_run=args.dry_run,
    )
    print(result.markdown)
    if result.contradictions and not args.dry_run:
        print("\n### Possible contradictions in today's batch\n", file=sys.stderr)
        for pair in result.contradictions[:5]:
            print(
                f"- ({pair.similarity:.2f}) {pair.a.title!r} vs {pair.b.title!r}",
                file=sys.stderr,
            )
    if result.path:
        print(f"\nSaved digest to {result.path}", file=sys.stderr)
    return 0


def _cmd_feedback(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    if not args.like and not args.dislike:
        print("Nothing to do: pass --like and/or --dislike with paper ids.")
        return 1
    profile = apply_feedback(
        config, args.like or [], args.dislike or [], user=args.user, reason=args.reason
    )
    print(
        f"Profile '{args.user}' updated from {len(args.like or [])} likes and "
        f"{len(args.dislike or [])} dislikes "
        f"({profile.n_feedback} feedback signals total)."
    )
    if args.reason in ("crowded", "weak-result", "already-tried"):
        if config.topics_db:
            print(f"Also logged {len(args.dislike or [])} dislike(s) to {config.topics_db}.")
        else:
            print("Set `topics_db` in paperpulse.yaml to also log this reason.")
    return 0


def _cmd_similar(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    results = find_similar_to_work(config, args.path, top_n=args.top_n)
    if not results:
        print("No papers fetched to compare against.")
        return 1
    print(f"Papers most similar to {args.path}:\n")
    for r in results:
        print(f"  {r.score:.3f}  {r.paper.title}  ({r.paper.id})")
    return 0


def _cmd_sources(_: argparse.Namespace) -> int:
    from .sources import available

    print("Available sources:", ", ".join(available()))
    return 0


def _cmd_note(args: argparse.Namespace) -> int:
    config = Config.load(args.config)
    if not config.community_db:
        print("Set `community_db` in paperpulse.yaml to use notes.")
        return 1
    from .community import CommunityDB

    db = CommunityDB(config.community_db)
    try:
        if args.text:
            db.add_note(args.paper_id, args.text, user=args.user)
            print(f"Noted on {args.paper_id}.")
        else:
            notes = db.get_notes(args.paper_id)
            if not notes:
                print(f"No notes on {args.paper_id}.")
            for n in notes:
                print(f"[{n['created_at']}] {n['user']}: {n['note']}")
    finally:
        db.close()
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .api import serve

    serve(host=args.host, port=args.port, config_path=args.config)
    return 0


def _cmd_factors_add(args: argparse.Namespace) -> int:
    from .topics import TopicLog

    config = Config.load(args.config)
    db_path = config.topics_db or "paperpulse_topics.db"
    log = TopicLog(db_path)
    try:
        log.add(
            args.name,
            aliases=args.aliases.split(",") if args.aliases else [],
            source=args.source,
            result=args.result,
            region=args.region or "",
            notes=args.notes or "",
        )
    finally:
        log.close()
    print(f"Logged '{args.name}' ({args.source}, {args.result}) to {db_path}.")
    return 0


def _cmd_factors_check(args: argparse.Namespace) -> int:
    """F2: run today's digest and report new evidence on tracked dead/weak
    factors -- "new" meaning not seen (matched) in the last 7 days."""
    from datetime import datetime, timedelta, timezone

    from .topics import TopicLog

    config = Config.load(args.config)
    if not config.topics_db:
        print("Set `topics_db` in paperpulse.yaml to use `factors check`.")
        return 1

    result = run_digest(config, dry_run=True)
    log = TopicLog(config.topics_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    hits = 0
    try:
        for item in result.ranked:
            if item.trust is None:
                continue
            matched = next(
                (s for s in item.trust.signals if s.name == "known_topic" and s.evidence),
                None,
            )
            if matched is None:
                continue
            entries = {e.name: e for e in log.all()}
            entry = entries.get(matched.evidence)
            if entry is None or entry.result not in ("dead", "weak"):
                continue
            is_new = not entry.last_seen_at or (
                datetime.fromisoformat(entry.last_seen_at) < cutoff
            )
            if is_new:
                hits += 1
                print(f"New evidence on '{entry.name}' ({entry.result}): {item.paper.title}")
            log.mark_seen(entry.name)
    finally:
        log.close()
    if not hits:
        print("No new evidence on tracked dead/weak factors in today's batch.")
    return 0


def _cmd_factors_list(args: argparse.Namespace) -> int:
    from .topics import TopicLog

    config = Config.load(args.config)
    db_path = config.topics_db or "paperpulse_topics.db"
    log = TopicLog(db_path)
    try:
        entries = log.all()
    finally:
        log.close()
    if not entries:
        print(f"No topics logged yet in {db_path}.")
        return 0
    for e in entries:
        aliases = f" [{', '.join(e.aliases)}]" if e.aliases else ""
        region = f" region={e.region}" if e.region else ""
        print(f"- {e.name}{aliases}: {e.source}/{e.result}{region} {e.notes}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperpulse", description="Relevance-ranked, trust-scored arXiv digests."
    )
    parser.add_argument("-c", "--config", default=None, help="path to paperpulse.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write a starter config file")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument(
        "--seed-avoid",
        default=None,
        metavar="FILE",
        help="comma/newline-separated factor names to seed `avoid_topics` from",
    )
    p_init.set_defaults(func=_cmd_init)

    p_run = sub.add_parser("run", help="fetch, rank, score, and write the digest")
    p_run.add_argument("--user", default="default")
    p_run.add_argument("--top-n", type=int, default=None)
    p_run.add_argument("--source", default=None, help="arxiv | biorxiv | pubmed")
    p_run.add_argument("--categories", nargs="+", default=None)
    p_run.add_argument("--llm", action="store_true", help="use an LLM for summaries")
    p_run.add_argument(
        "--online", action="store_true", help="enable network trust checks"
    )
    p_run.add_argument("--include-seen", action="store_true")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_fb = sub.add_parser("feedback", help="teach the ranker from paper ids")
    p_fb.add_argument("--user", default="default")
    p_fb.add_argument("--like", nargs="+", default=None, metavar="ID")
    p_fb.add_argument("--dislike", nargs="+", default=None, metavar="ID")
    p_fb.add_argument(
        "--reason",
        choices=["irrelevant", "crowded", "weak-result", "already-tried"],
        default=None,
        help="why the dislikes were disliked; crowded/weak-result/already-tried "
        "also log the topic to `topics_db`",
    )
    p_fb.set_defaults(func=_cmd_feedback)

    p_sim = sub.add_parser(
        "similar", help="find papers similar to your code / notebook"
    )
    p_sim.add_argument("path", help="path to a .py / .ipynb file")
    p_sim.add_argument("--top-n", type=int, default=10)
    p_sim.set_defaults(func=_cmd_similar)

    p_note = sub.add_parser("note", help="add or list notes on a paper (needs community_db)")
    p_note.add_argument("paper_id")
    p_note.add_argument("text", nargs="?", default=None, help="omit to list existing notes")
    p_note.add_argument("--user", default="default")
    p_note.set_defaults(func=_cmd_note)

    p_factors = sub.add_parser(
        "factors", help="known/already-tried factor log (shared by A2 + D2)"
    )
    factors_sub = p_factors.add_subparsers(dest="factors_command", required=True)

    p_factors_add = factors_sub.add_parser("add", help="log a factor/topic")
    p_factors_add.add_argument("name")
    p_factors_add.add_argument("--aliases", default=None, help="comma-separated")
    p_factors_add.add_argument(
        "--source", choices=["manual", "literature"], default="manual"
    )
    p_factors_add.add_argument(
        "--result", choices=sorted({"dead", "weak", "promising", "untested"}), default="untested"
    )
    p_factors_add.add_argument("--region", default=None)
    p_factors_add.add_argument("--notes", default=None)
    p_factors_add.set_defaults(func=_cmd_factors_add)

    p_factors_list = factors_sub.add_parser("list", help="list logged factors/topics")
    p_factors_list.set_defaults(func=_cmd_factors_list)

    p_factors_check = factors_sub.add_parser(
        "check", help="run today's digest and report new evidence on tracked dead/weak factors (F2)"
    )
    p_factors_check.set_defaults(func=_cmd_factors_check)

    p_src = sub.add_parser("sources", help="list available paper sources")
    p_src.set_defaults(func=_cmd_sources)

    p_serve = sub.add_parser("serve", help="run the REST API + web dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
