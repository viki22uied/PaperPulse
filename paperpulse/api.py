"""REST API and a minimal web dashboard.

Built on the standard library's ``http.server`` so ``paperpulse serve`` works
with no extra dependencies -- handy for self-hosting. It exposes the same
capabilities as the CLI:

    GET  /                       -> HTML dashboard (renders the digest)
    GET  /api/sources            -> available paper sources
    GET  /api/digest             -> ranked papers + trust as JSON
    POST /api/feedback           -> {"like": [...], "dislike": [...]}
    GET  /api/community/leaderboard
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import Config
from .pipeline import apply_feedback, run_digest
from .sources import available

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>PaperPulse</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#111}}
 h1{{margin-bottom:.2rem}} .sub{{color:#666}}
 .card{{border:1px solid #e3e3e3;border-radius:10px;padding:1rem 1.2rem;margin:1rem 0}}
 .bar{{font-family:ui-monospace,monospace;color:#3157ff}}
 .badge{{font-size:.8rem;padding:.1rem .5rem;border-radius:99px;color:#fff}}
 .clean{{background:#1a9d55}} .mixed{{background:#c98a00}} .caution{{background:#c0392b}}
 .flag{{color:#b23}} a{{color:#3157ff;text-decoration:none}}
 @media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}.card{{border-color:#333}}}}
</style></head><body>
<h1>PaperPulse</h1><div class="sub">{subtitle}</div>
{cards}
</body></html>"""

_CARD = """<div class="card">
 <h3>{i}. {title}</h3>
 <div class="bar">{bar} relevance {score:.2f} <span class="badge {badge}">{badge}</span></div>
 <p>{summary}</p>
 {flags}
 <div><a href="{url}">abstract</a> · <code>{pid}</code></div>
</div>"""


def _bar(score: float, width: int = 12) -> str:
    filled = max(0, min(width, round(score * width)))
    return "█" * filled + "░" * (width - filled)


def _render_dashboard(config: Config) -> str:
    result = run_digest(config, dry_run=True)
    cards = []
    for i, item in enumerate(result.ranked, start=1):
        badge = getattr(item.trust, "badge", "clean") if item.trust else "clean"
        flags = ""
        if item.trust and item.trust.flags:
            flags = "<ul>" + "".join(
                f'<li class="flag">{s.name}: {s.note}</li>' for s in item.trust.flags
            ) + "</ul>"
        cards.append(
            _CARD.format(
                i=i,
                title=item.paper.title,
                bar=_bar(item.score),
                score=item.score,
                badge=badge,
                summary=(item.summary or ""),
                flags=flags,
                url=item.paper.url,
                pid=item.paper.id,
            )
        )
    subtitle = f"{config.source} · " + " · ".join(config.categories)
    return _PAGE.format(subtitle=subtitle, cards="\n".join(cards) or "<p>No papers.</p>")


def _digest_json(config: Config) -> dict:
    result = run_digest(config, dry_run=True)
    return {
        "papers": [
            {
                "id": item.paper.id,
                "title": item.paper.title,
                "score": round(item.score, 4),
                "summary": item.summary,
                "url": item.paper.url,
                "trust": None
                if item.trust is None
                else {
                    "score": item.trust.score,
                    "badge": item.trust.badge,
                    "flags": [
                        {"name": s.name, "status": s.status, "note": s.note}
                        for s in item.trust.flags
                    ],
                },
            }
            for item in result.ranked
        ],
        "contradictions": [
            {"a": p.a.id, "b": p.b.id, "similarity": round(p.similarity, 3)}
            for p in result.contradictions
        ],
    }


def make_handler(config: Config):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # keep the console quiet
            pass

        def _send(self, code: int, body: str, content_type: str) -> None:
            payload = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj), "application/json")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, _render_dashboard(config), "text/html; charset=utf-8")
            elif path == "/api/sources":
                self._json({"sources": available()})
            elif path == "/api/digest":
                self._json(_digest_json(config))
            elif path == "/api/community/leaderboard":
                if not config.community_db:
                    self._json({"error": "community_db not configured"}, 400)
                    return
                from .community import CommunityDB

                db = CommunityDB(config.community_db)
                try:
                    self._json({"leaderboard": db.flag_leaderboard()})
                finally:
                    db.close()
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return
            if path == "/api/feedback":
                profile = apply_feedback(
                    config,
                    list(body.get("like", [])),
                    list(body.get("dislike", [])),
                    user=body.get("user", "default"),
                )
                self._json({"ok": True, "n_feedback": profile.n_feedback})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(*, host: str = "127.0.0.1", port: int = 8000, config_path=None) -> None:
    config = Config.load(config_path)
    server = ThreadingHTTPServer((host, port), make_handler(config))
    print(f"PaperPulse serving on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


__all__ = ["serve", "make_handler"]
