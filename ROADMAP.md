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
- ✅ Semantic (embedding) cross-reference against the log, beyond the current
  deterministic name/alias match -- opt-in via `known_topics_semantic: true`.
  The exact name/alias match always wins; this only runs as a fallback when it
  finds nothing, so a paraphrase ("female representation among corporate
  directors" vs a logged "board diversity") still matches. The log is embedded
  once per run and compared against the vector already computed for ranking.
  The flag stays explainable: `note` says "exact match" vs "semantic match,
  cosine 0.58", and a semantic hit carries 0.7x the confidence of an exact one.
  Validated against a 12-abstract labeled sample
  (`tests/test_known_topics_semantic.py`): with sentence-transformers,
  **0% false positives (0/7), 100% true positives (5/5)** at the default 0.35
  threshold -- chosen as the max-margin split between the highest negative
  (0.29, "board size and director independence": same governance vocabulary,
  different topic) and the lowest positive (0.40).
  🔴 **Inert on the default hashing backend** (measured tp=0/5): a bag of word
  n-grams shares no tokens with a paraphrase, so paraphrases score 0.00-0.06
  and nothing clears the threshold. It fails safe -- silent, never misfiring --
  but needs the `semantic` extra to do anything. Off by default for that reason.

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
- ✅ "What changed since last week" diff for a tracked subfield: `paperpulse
  diff` / `GET /api/diff` / a "Since last week" toggle in the dashboard. Each
  non-dry `run` records a snapshot (ranked ids, scores, trust badges, flags,
  contradiction polarities) into the existing state file, keyed by sorted
  category set so a q-fin digest never diffs against a cs.LG one (capped at 20
  per key). The diff reports (a) papers absent from the last snapshot, (b) fresh
  evidence on a tracked dead/weak factor -- the same `last_seen_at` logic as
  `factors check`, lifted out of the CLI into `pipeline.new_factor_evidence` so
  both share it, and (c) contradiction pairs whose disagreement reversed
  direction. Runs with `skip_seen=False` deliberately: the normal digest hides
  already-shown papers, which would make every survivor look new. Read-only by
  default (`--mark` opts into writing `last_seen_at`; `GET /api/diff` never
  does, so it stays safe to repeat). Covered offline by `tests/test_diff.py`
  (5 tests, synthetic batches, no network).
- ⏳ Citation-trail contradiction (needs reference resolution / full text)

## Cross-referencing your own work
- ✅ Paste code/notebook → rank papers by method-level similarity
- ⏳ Structured method-vs-implementation diff

## Dashboard / tracked-factor UX
- ✅ Dashboard filter presets (F1): one-click "Region: USA only", "Known
  factor families only", "Untested regions only" buttons in the web
  dashboard, filtering client-side over the already-fetched digest.
- ✅ `paperpulse factors check` (F2): re-runs today's digest and reports
  "new evidence" on any tracked dead/weak factor -- new meaning not matched
  in the last 7 days (`last_seen_at` on the shared topics log).

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
- ✅ Per-paper annotation layer (`paperpulse note`, needs `community_db`)
- ⏳ Hosted public instance + moderation

## Infra / meta
- ✅ CLI + Python SDK + REST API — three ways to use it
- ✅ First-run UX (0.2.0): interactive `init` wizard + `--preset` topic packs,
  live progress during `run`, one-line friendly errors with `--debug` escape
- ✅ Hardening (0.2.0): opt-in `PAPERPULSE_API_TOKEN` on API writes; PDF
  fetches restricted to https + known publisher hosts
- ✅ Self-hostable via Docker / docker-compose
- ✅ Config-driven sources / signals / delivery
- ✅ Offline test suite, CI across Python 3.10–3.12
- ✅ End-to-end verification: `tests/test_end_to_end_roadmap.py` seeds
  `avoid_topics` + a `topics_db` "dead" entry for board diversity, runs a
  full digest against a synthetic batch, and confirms the board-diversity
  paper both scores lower than unrelated papers (avoid_topics) and carries
  a `known_topic` flag citing the logged reason (A1/A2/D2 working together)
