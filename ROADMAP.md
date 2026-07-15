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
- 🟡 SSRN source (C2), via OpenAlex rather than a direct scraper -- spike
  found no official SSRN API, and existing third-party scrapers sit in a
  ToS/robots.txt grey area we didn't want to inherit. OpenAlex indexes SSRN
  as a first-class source ("SSRN Electronic Journal", ~1.6M works) through
  its own free, keyless, official REST API, so `paperpulse/sources/ssrn.py`
  never touches ssrn.com directly. `paperpulse run --source ssrn`.
- ⏳ OpenReview adapter (interface ready — one class)
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
- ✅ Weak/null-result badge (`weak_result` signal): regex over full text
  (falls back to the abstract) for weak-result language, with a same-sentence
  override so positive framings ("no significant difference ... confirming
  robustness") don't misfire. Validated against a 20-abstract labeled sample
  (`tests/test_weak_result_validation.py`): 0% false positives, 90% true
  positives -- stays a soft WARN badge regardless, never a hard FLAG, since
  it's pattern-matching on the *finding*, not the methodology.
- ⏳ Author conflict-of-interest flag — needs author-affiliation data (not in the arXiv feed)
- ⏳ "Related work" completeness / citation-graph gaps — needs a citation graph (Semantic Scholar)
- ⏳ Figure/table manipulation heuristics — needs figure/table extraction from PDFs
- ⏳ Compute/resource reality check beyond keyword flags
- ⏳ Replication-status tracker

## Known factor families / already-tried log
- ✅ Shared SQLite log (`topics_db`) unifying "known factor family from the
  literature" and "I already tried this myself" -- `source` field
  distinguishes them, `result` (dead/weak/promising/untested) drives the flag
- ✅ `paperpulse factors add "name" --aliases a,b --source manual|literature
  --result dead|weak|promising|untested` / `paperpulse factors list`
- ✅ Fully offline `known_topic` trust signal: exact/near-exact name-or-alias
  match against title+abstract -- 🔴 flag if logged dead/weak, 🟡 warn if it's
  a known factor family with no verdict yet
- ✅ `--reason crowded|weak-result|already-tried` on `paperpulse feedback
  --dislike` auto-logs the disliked paper's title into this same log
  (`crowded`/`weak-result` -> `weak`, `already-tried` -> `dead`;
  `irrelevant` logs nothing, since it says nothing about the topic itself)
- ✅ Inverse interest profile: `avoid_topics` + `avoid_weight` in config are
  embedded and subtracted straight from the ranking score, so a topic you've
  already exhausted ranks lower from the very first run (cold start, no
  feedback needed). Seed it with `paperpulse init --seed-avoid factors.txt`.
- ⏳ Semantic (embedding) cross-reference against the log, beyond the current
  deterministic name/alias match

## Region / market relevance
- ✅ Keyword-based region auto-tagging (`paperpulse/region.py`): USA / EUR /
  CHN / IND from index/market names, else `Global/Unspecified`. Shown per
  paper in the digest and REST API (`regions` field).
- ✅ `region_filter` config to restrict digests to specific regions (with
  `Global/Unspecified` kept by default via `region_filter_include_unspecified`)
- ✅ Cross-region transfer flag: `already_tested_regions` maps a known-topics
  entry to the regions you've already tested it in; a matched topic in an
  untested region gets a green "may still be valid to explore" note instead
  of being suppressed like a same-region repeat would be

## Quant-derived trust signals
- ✅ Novelty-vs-crowding score (batch embedding similarity)
- ✅ Subgroup-robustness check
- ✅ Metric-gaming detector
- ✅ Benchmark-saturation flag
- ✅ Real-world deployability check
- ✅ Backtest-overfitting flag (no out-of-sample / walk-forward / cost check)
- ✅ Survivorship-bias flag (E1): backtest with no mention of delisted/failed firms
- ✅ Transaction-cost-omission flag (E1): trading strategy with no cost/slippage mention
- ✅ Single-market/period flag (E1): no mention of testing across regimes/markets/periods
- ✅ Novelty vs. known literature (E2): `literature_novelty` signal compares
  each paper against a fixed canonical-factor reference set (Fama-French,
  Carhart, momentum, betting-against-beta, quality-minus-junk, gross
  profitability, low-vol anomaly) plus the known-topics log, independent of
  today's batch. Validated per the shared sub-requirement
  (`tests/test_literature_novelty.py`): 0% false positives, 80% true
  positives with the default hashing backend -- soft WARN only, never FLAG.
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
