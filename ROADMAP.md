# Roadmap

Status of each feature. ✅ Shipped and tested. 🟡 Implemented, needs live keys or services to fully validate. ⏳ Planned.

The offline core is covered by the test suite. This includes ranking, feedback, trust checks, contradiction mapping, cross-referencing, digest rendering, RSS, community database, and REST API. Network features (source APIs, SMTP, webhooks, Retraction Watch, LLM summaries) use their real interfaces. You must test these features when keys and network access are available. They fail safely until then.

## Ingestion and Coverage

- ✅ arXiv API: pull papers by category, keyword, or author
- 🟡 bioRxiv / medRxiv source (real API; needs live validation)
- 🟡 PubMed source through NCBI E-utilities (real API; `NCBI_API_KEY` optional)
- 🟡 SSRN source through OpenAlex. There is no official SSRN API. OpenAlex indexes SSRN as a first-class source (~1.6M works) through its free REST API. The module `paperpulse/sources/ssrn.py` does not connect to ssrn.com directly. Use `paperpulse run --source ssrn`.
- ⏳ OpenReview adapter (interface is ready; one class)
- 🟡 Scheduled daily/weekly runs (cron and GitHub Action provided)
- ✅ Full-text PDF parsing (`paperpulse[pdf]`, `--full-text`). Fetches each PDF once. Trust signals and alpha cards share the parsed text. The parser removes related-work and reference sections. This prevents attribution of other papers' numbers to the current paper.
- ⏳ Table and figure extraction from PDFs

## Relevance and Personalization

- ✅ Interest profile through embeddings (paragraph or seed papers)
- ✅ Thumbs up/down feedback loop (Rocchio algorithm) to refine ranking
- ✅ Multi-user support with separate profiles
- ✅ "Similar to a paper I liked" recommendations
- ✅ MMR diversity in top-N selection

## Trust and Reproducibility

- ✅ Over-claiming detector: checks for assertive language without hedging
- ✅ Evidence check: looks for error bars and significance statements
- ✅ Baseline-fairness check
- ✅ Dataset-leakage flag: detects random splits on time-series or finance data
- ✅ Reproducibility check: looks for code and data links
- ✅ Peer-review and venue status from arXiv metadata (published vs. preprint; flags old unaccepted papers)
- ✅ Per-flag evidence: shows the exact phrase that caused each flag. Each signal has a confidence value.
- ✅ Priority score: relevance multiplied by trust
- 🟡 Dead code/data link detection (`--online`)
- 🟡 Retraction Watch cross-check (`--online`)
- 🟡 Self-citation ratio through Semantic Scholar (`--online`; `S2_API_KEY` optional)
- ✅ Weak/null-result badge (`weak_result` signal). Scans full text (or abstract) for weak-result language. A same-sentence override prevents false positives from positive framings. Validated against a 20-abstract sample (`tests/test_weak_result_validation.py`): 0% false positives, 90% true positives. This is a soft WARN badge, not a hard FLAG. It detects the finding, not the methodology.
- ⏳ Author conflict-of-interest flag (needs author-affiliation data)
- ⏳ Related-work completeness and citation-graph gaps (needs Semantic Scholar)
- ⏳ Figure/table manipulation detection (needs extraction from PDFs)
- ⏳ Compute/resource reality check beyond keyword flags
- ✅ Prospective flag-validation ledger (0.6.0). An immutable store (`validation_db`) records every trust flag at assessment time. Three reconcilers check against ground truth: retraction (Crossref + OpenAlex), citation decline, and out-of-sample decay (Chen-Zimmermann data). Reports per-badge-tier calibration with Brier scores and lift over the base rate. Use `paperpulse reconcile`, `paperpulse calibration`, or `GET /api/calibration`.
- ⏳ FORRT/FLoRA replication-database reconciler (awaiting a stable API)

## Known Factor Families and Already-Tried Log

- ✅ Shared SQLite log (`topics_db`). Stores known factor families from the literature and topics you already tried. The `source` field separates them. The `result` field (dead/weak/promising/untested) controls the flag.
- ✅ `paperpulse factors add "name" --aliases a,b --source manual|literature --result dead|weak|promising|untested` and `paperpulse factors list`
- ✅ Offline `known_topic` trust signal. Does an exact or near-exact name/alias match against the title and abstract. Shows a red flag if the topic is logged as dead or weak. Shows a yellow warning if the topic is known but has no verdict.
- ✅ `--reason crowded|weak-result|already-tried` on `paperpulse feedback --dislike`. This logs the paper's title into the topics log automatically. "crowded" and "weak-result" set the result to "weak". "already-tried" sets it to "dead". "irrelevant" does not log anything.
- ✅ Inverse interest profile. `avoid_topics` and `avoid_weight` in the config are embedded and subtracted from the ranking score. Topics you have exhausted rank lower from the first run. Seed it with `paperpulse init --seed-avoid factors.txt`.
- ✅ Semantic cross-reference against the log. Opt in with `known_topics_semantic: true`. The exact name/alias match takes priority. The semantic match runs only as a fallback when the exact match finds nothing. This catches paraphrases (e.g., "female representation among corporate directors" matches "board diversity"). The flag note shows "exact match" or "semantic match, cosine 0.58". A semantic hit carries 0.7x the confidence of an exact hit. Validated against a 12-abstract sample (`tests/test_known_topics_semantic.py`): 0% false positives (0/7), 100% true positives (5/5) at the default 0.35 threshold. **Does not work on the default hashing backend** (0/5 true positives). Needs the `semantic` extra. Off by default.

## Region and Market Relevance

- ✅ Keyword-based region auto-tagging (`paperpulse/region.py`). Tags papers as USA, EUR, CHN, or IND based on index and market names. Defaults to Global/Unspecified. Shows per paper in the digest and REST API (`regions` field).
- ✅ `region_filter` config. Restricts digests to specific regions. Keeps Global/Unspecified by default (`region_filter_include_unspecified`).
- ✅ Cross-region transfer flag. `already_tested_regions` maps a known topic to the regions where you already tested it. A matched topic in an untested region gets a green "may still be valid to explore" note. A same-region match is suppressed as a repeat.

## Quantitative Trust Signals

- ✅ Alpha cards (0.2.0). Extracts each finance paper's testable claim: predictor, target, datasets, effect sizes, universe, and period. Rates testability. Available through `paperpulse alpha`, the digest, the dashboard, and the API. `--full-text` reads the PDF for data that the abstract does not include.
- ✅ Novelty-vs-crowding score (batch embedding similarity)
- ✅ Subgroup-robustness check
- ✅ Metric-gaming detector
- ✅ Benchmark-saturation flag
- ✅ Real-world deployability check
- ✅ Backtest-overfitting flag: no out-of-sample, walk-forward, or cost check
- ✅ Survivorship-bias flag: backtest with no mention of delisted or failed firms
- ✅ Transaction-cost-omission flag: trading strategy with no cost or slippage mention
- ✅ Single-market/period flag: no mention of testing across regimes, markets, or periods
- ✅ Novelty vs. known literature: `literature_novelty` signal compares each paper against a fixed canonical-factor set (Fama-French, Carhart, momentum, betting-against-beta, quality-minus-junk, gross profitability, low-vol anomaly) and the known-topics log. Validated (`tests/test_literature_novelty.py`): 0% false positives, 80% true positives on the default hashing backend. Soft WARN only, not a FLAG.
- ✅ Factor-zoo hurdle signal. Flags t-stats between 1.96 and 3.0 as below the Harvey-Liu multiple-testing threshold for the 300+ factor zoo.
- ✅ Deflation-gap signal. Flags Sharpe ratios or t-stats reported without trial counts or multiple-testing correction (Bailey and de Prado DSR/PBO gap).
- ✅ No-OOS-validation signal. Flags quantitative finance claims with no mention of out-of-sample, walk-forward, or holdout validation.
- ⏳ Config-driven per-domain confound checklists

## Contradiction and Context Mapping

- ✅ Multi-paper contradiction map for a batch (similarity + opposing polarity)
- ✅ "What changed since last week" diff for a tracked subfield. Use `paperpulse diff`, `GET /api/diff`, or the dashboard toggle. Each non-dry run records a snapshot (ranked IDs, scores, trust badges, flags, contradiction polarities) to the state file. Snapshots are keyed by category set so different subfields do not mix. The diff reports: (a) papers absent from the last snapshot, (b) new evidence on a tracked dead/weak factor, and (c) contradiction pairs that reversed direction. Runs with `skip_seen=False` so that papers that persist between snapshots do not appear as new. Read-only by default. Use `--mark` to write `last_seen_at`. `GET /api/diff` never writes. Covered by `tests/test_diff.py` (5 tests, synthetic data, no network).
- ✅ Polarity-flip monitor (0.6.0). Stores per-pair polarity time-series in SQLite (`polarity_db`). Detects polarity flips automatically. Reports per-pair consensus volatility. Use `paperpulse polarity` to see tracked pairs, recent flips, and the most volatile pairs.
- ⏳ Citation-trail contradiction (needs reference resolution or full text)

## Cross-Referencing Your Own Work

- ✅ Paste code or notebook to rank papers by method-level similarity
- ⏳ Structured method-vs-implementation diff

## Dashboard and Tracked-Factor UX

- ✅ Dashboard filter presets: one-click buttons for "Region: USA only", "Known factor families only", and "Untested regions only". Filters run client-side on the already-fetched digest.
- ✅ `paperpulse factors check`. Re-runs today's digest and reports new evidence on any tracked dead/weak factor. "New" means the match was not seen in the last 7 days (`last_seen_at` on the shared topics log).

## Summarization and Delivery

- ✅ Three-bullet plain-English digest (extractive by default; LLM is optional)
- ✅ Trust-score badge with each summary
- ✅ Markdown digest output
- ✅ JSON digest output (`paperpulse run --format json`). Same structure as `GET /api/digest`. Use this for scripts, dashboards, and scheduled jobs.
- ✅ BibTeX export (`paperpulse export`). Creates entries for Zotero, Mendeley, EndNote, or LaTeX. arXiv IDs get proper `eprint` and `archivePrefix` fields.
- 🟡 Email delivery (SMTP)
- ✅ RSS feed output
- ✅ Web dashboard and REST API (uses the standard library; self-hostable)
- ✅ Browser setup panel (GET/POST `/api/config`). The dashboard equivalent of `paperpulse init`. Select a topic pack or write your own interests text. Saves to `paperpulse.yaml`.
- ✅ LaTeX rendering in abstracts and claims (KaTeX). Renders math correctly, including bare `\begin{equation*}` blocks.
- 🟡 Slack and Discord delivery (incoming webhooks)

## Community and Social Layer

- ✅ Self-hostable shared trust store (SQLite). Teams can pool scores across users.
- ✅ Over-claiming leaderboard by author and venue
- ✅ Per-paper annotation layer (`paperpulse note`, needs `community_db`)
- ✅ Flag-survival benchmark (0.6.0). Tracks per-signal precision against realized outcomes across all users. `paperpulse flag-survival` reports which signals have the best confirmed-vs-false-positive rate.
- ⏳ Hosted public instance with moderation

## Infrastructure

- ✅ CLI, Python SDK, and REST API: three ways to use PaperPulse
- ✅ First-run setup (0.2.0): interactive `init` wizard, `--preset` topic packs, progress display during `run`, clear error messages with `--debug`
- ✅ Security hardening (0.2.0): opt-in `PAPERPULSE_API_TOKEN` on API writes. PDF fetches restricted to HTTPS and known publisher hosts.
- ✅ Security hardening (0.5.0): `PAPERPULSE_API_TOKEN` now guards every route (GET included). All outbound requests that use a host allowlist go through a shared no-redirect opener (`netguard.py`). An approved host cannot redirect a request to an unapproved host.
- ✅ Self-hostable with Docker and docker-compose
- ✅ Config-driven sources, signals, and delivery
- ✅ Offline test suite. CI runs across Python 3.10, 3.11, and 3.12.
- ✅ End-to-end verification (`tests/test_end_to_end_roadmap.py`). Seeds `avoid_topics` and a dead entry for "board diversity" in `topics_db`. Runs a full digest against a synthetic batch. Confirms that the board-diversity paper scores lower (avoid_topics) and carries a `known_topic` flag with the logged reason.
