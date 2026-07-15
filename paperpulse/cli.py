"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from .config import Config, DEFAULT_CONFIG_PATH
from .pipeline import apply_feedback, find_similar_to_work, run_digest


def _cmd_init(args: argparse.Namespace) -> int:
    if DEFAULT_CONFIG_PATH.exists() and not args.force:
        print(f"{DEFAULT_CONFIG_PATH} already exists (use --force to overwrite).")
        return 1
    path = Config().save()
    print(
        f"Wrote starter config to {path}. Edit `interests`, `categories`, and "
        f"`source`, then run `paperpulse run`."
    )
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
        config, args.like or [], args.dislike or [], user=args.user
    )
    print(
        f"Profile '{args.user}' updated from {len(args.like or [])} likes and "
        f"{len(args.dislike or [])} dislikes "
        f"({profile.n_feedback} feedback signals total)."
    )
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperpulse", description="Relevance-ranked, trust-scored arXiv digests."
    )
    parser.add_argument("-c", "--config", default=None, help="path to paperpulse.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="write a starter config file")
    p_init.add_argument("--force", action="store_true")
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
