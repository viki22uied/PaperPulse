# Roadmap

Honest status of the full feature vision. ✅ shipped and tested · 🟡 implemented,
needs live keys/services to fully validate · ⏳ planned.

The offline core (ranking, feedback, trust heuristics, contradiction mapping,
cross-referencing, digest rendering, RSS, community DB, REST API) is covered by
the test suite. Network paths (live source APIs, SMTP, webhooks, Retraction
Watch, LLM summaries) are implemented against their real interfaces but are
exercised by you once keys/egress are in place — they fail soft until then.

## Ingestion & coverage
- ✅ arXiv API pull by category / keyword / author
- 🟡 bioRxiv / medRxiv source (real API; validate live)
- 🟡 PubMed source via NCBI E-utilities (real API; `NCBI_API_KEY` optional)
- ⏳ OpenReview and SSRN adapters (interface ready — one class each)
- 🟡 Scheduled daily/weekly runs (cron + GitHub Action provided)
- ⏳ Full-text PDF parsing and table/figure extraction

## Relevance & personalization
- ✅ Interest profile via embeddings (paragraph and/or seed papers)
- ✅ Thumbs up/down feedback loop (Rocchio) refining ranking
- ✅ Multi-user support with separate profiles
- ✅ "Similar to a paper/work I liked" recommendations
- ✅ MMR diversity in top-N selection

## Trust & reproducibility
- ✅ Over-claiming detector (assertive-vs-hedged language)
- ✅ Evidence / error-bar / significance presence check
- ✅ Baseline-fairness heuristic
- ✅ Dataset-leakage red flag (random splits on time-series/finance)
- ✅ Reproducibility (code/data link presence)
- ✅ Peer-review / venue status from arXiv metadata (published vs preprint; flags stale-unaccepted)
- ✅ Per-flag evidence (the exact phrase that tripped it) + per-signal confidence
- ✅ "Worth-it" priority score (relevance × trust)
- 🟡 Dead code/data link detection (`--online`)
- 🟡 Retraction Watch cross-check (`--online`)
- 🟡 Self-citation ratio via Semantic Scholar (`--online`; `S2_API_KEY` optional)
- ⏳ Author conflict-of-interest flag — needs author-affiliation data (not in the arXiv feed)
- ⏳ "Related work" completeness / citation-graph gaps — needs a citation graph (Semantic Scholar)
- ⏳ Figure/table manipulation heuristics — needs figure/table extraction from PDFs
- ⏳ Compute/resource reality check beyond keyword flags
- ⏳ Replication-status tracker

## Quant-derived trust signals
- ✅ Novelty-vs-crowding score (batch embedding similarity)
- ✅ Subgroup-robustness check
- ✅ Metric-gaming detector
- ✅ Benchmark-saturation flag
- ✅ Real-world deployability check
- ✅ Backtest-overfitting flag (no out-of-sample / walk-forward / cost check)
- ⏳ Config-driven per-domain confound checklists (scaffold in config)

## Contradiction & context mapping
- ✅ Multi-paper contradiction map for a batch (similarity + opposing polarity)
- ⏳ "What changed since last week" diff for a tracked subfield
- ⏳ Citation-trail contradiction (needs reference resolution / full text)

## Cross-referencing your own work
- ✅ Paste code/notebook → rank papers by method-level similarity
- ⏳ Structured method-vs-implementation diff

## Summarization & delivery
- ✅ 3-bullet plain-English digest (extractive default; LLM optional)
- ✅ Trust-score badge alongside each summary
- ✅ Markdown digest output
- 🟡 Email delivery (SMTP)
- ✅ RSS feed output
- ✅ Simple web dashboard + REST API (stdlib, self-hostable)
- 🟡 Slack / Discord delivery (incoming webhooks)

## Community / social layer
- ✅ Self-hostable shared trust store (SQLite) to pool scores across users
- ✅ Over-claiming leaderboard by author/venue
- ⏳ Per-paper annotation layer (PubPeer-style)
- ⏳ Hosted public instance + moderation

## Infra / meta
- ✅ CLI + Python SDK + REST API — three ways to use it
- ✅ Self-hostable via Docker / docker-compose
- ✅ Config-driven sources / signals / delivery
- ✅ Offline test suite, CI across Python 3.10–3.12
