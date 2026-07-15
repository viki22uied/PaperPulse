# PaperPulse

[![CI](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperpulse)](https://pypi.org/project/paperpulse/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**The five papers that actually matter to you today — ranked, trust-scored, and summarised in plain English.**

📄 **[See a real digest generated today →](examples/2026-07-14.md)** &nbsp;·&nbsp;
🗺️ **[Roadmap](ROADMAP.md)** &nbsp;·&nbsp;
🧪 **[Annotated sample](examples/sample-digest.md)**

arXiv drops hundreds of papers a day. Summaries are a solved problem; *triage*
isn't. PaperPulse is built around the two questions that actually waste your
time:

1. **Which of today's 200 papers are relevant to *me*?** — a learnable interest
   profile ranks every abstract by similarity to what you care about, a
   thumbs-up/down feedback loop sharpens it over time, and `avoid_topics` ranks
   down factors you've already worked to death — even before any feedback.
2. **Which of those should I actually trust?** — a set of offline *signal-quality*
   heuristics flag over-claiming, missing error bars, weak baselines, likely data
   leakage, benchmark-chasing, weak/null results, and incremental "me-too" work,
   before you sink twenty minutes into the PDF.
3. **Have I already been down this road?** — a shared known-factor /
   already-tried log flags papers matching something you (or the literature)
   already found dead, weak, or crowded — and green-lights the same factor in
   a region you haven't tested yet.

It runs out of the box with **no API keys and no model downloads** (local hashing
embeddings + extractive summaries), and scales up cleanly to semantic embeddings
and LLM summaries when you want them.

```bash
pip install paperpulse    # or: pip install -e .  (from a clone)
paperpulse init           # write a starter paperpulse.yaml
# edit `interests` and `categories`
paperpulse run            # today's ranked, trust-scored digest -> digests/YYYY-MM-DD.md
```

The [sample digest](examples/sample-digest.md) is annotated to show the finance
paper getting a 🚩 *leakage* flag and the hype paper collecting four flags while a
careful LoRA study rises to the top.

---

## Why it's not just another arXiv scraper

| | Typical "arXiv + LLM" script | PaperPulse |
|---|---|---|
| Ranking | none / recency | learnable interest vector + **MMR diversity** + `avoid_topics` |
| Personalisation | static keywords | **Rocchio feedback loop**, per-user profiles |
| Trust | blind trust in the summary | **15+ signal-quality checks** with a badge |
| Novelty | — | **crowding score** + **known/already-tried factor log** flag incremental or dead-end work |
| Cost to start | API key required | **runs fully offline** |

## How the ranking works

1. **Embed** each abstract into a stable vector space. The default
   `HashingBackend` needs no model and no training, so a profile learned today is
   still comparable next week. Install `paperpulse[semantic]` to switch to
   sentence-transformers for sharper semantics — same interface, better vectors.
2. **Score** by cosine similarity to your interest vector, minus a weighted
   pull away from anything in `avoid_topics` — factor names you're already
   sick of, seeded in bulk with `paperpulse init --seed-avoid factors.txt`.
3. **Select** the top *N* with **Maximal Marginal Relevance**, trading a little
   relevance for variety so you don't get five near-identical papers.
4. **Learn.** `paperpulse feedback --like 2407.00004 --dislike 2407.00002`
   nudges the profile toward what you liked and away from what you didn't
   (Rocchio), anchored so it never drifts far from the interests you wrote down.
   Add `--reason crowded|weak-result|already-tried` and the dislike also gets
   logged to the known-topics store below, instead of only nudging a vector.

## The trust layer

Working from a title and abstract we can't *prove* a paper is sound — but we can
cheaply flag the patterns that correlate with weaker work. Each signal is
deterministic, explains itself, and rolls up into a 🟢 clean / 🟡 mixed /
🔴 caution badge. Any hard red flag keeps a paper out of "clean".

Every flag is **legible**: it shows the *exact phrase that tripped it* and a
*confidence* so you can dismiss weak heuristics at a glance, not just a colour.
A **peer-review / venue** signal separates published or venue-accepted work from
preprint-only (and flags papers that have sat on arXiv for years, still v1, with
no venue). Each paper also carries a **worth-it** score — relevance × trust — to
answer "is this worth my next 30 minutes?"

Several are drawn straight from systematic-trading research discipline:

- **crowding / novelty** — is the method a cosmetic rehash of neighbours in the same batch?
- **literature novelty** — is it a rehash of a well-known factor (Fama-French, Carhart,
  momentum, betting-against-beta, quality-minus-junk, gross profitability, low-vol),
  independent of what else arrived today?
- **known/already-tried factor** — does it match something logged as dead, weak, or
  merely a known factor family in your shared topics log? (see below)
- **weak/null result** — does the abstract or full text actually say "no significant
  improvement", "inconclusive", "fails to replicate" — separate from methodology quality
- **subgroup robustness** — do strong aggregate numbers hide weak subgroups?
- **metric gaming** — did a metric move without a genuine underlying gain?
- **deployability** — oracle inputs, look-ahead features, or unrealistic compute?
- **leakage** — random splits on time-series/financial data (a classic lookahead trap)
- **backtest overfitting, survivorship bias, transaction-cost omission, single-market/period**
  — a backtest with no out-of-sample check, no mention of delisted firms, no costs, or
  tested on only one market/window
- **baseline fairness**, **evidence / error bars**, **over-claiming**, **benchmark saturation**, **reproducibility (code/data links)**

Turn on `--online` (or `trust_online: true`) to add **dead-link detection**, a
**Retraction Watch** cross-check, a **self-citation ratio** (via Semantic
Scholar — set `S2_API_KEY` for higher rate limits), a **citation-graph gap**
check (thin reference lists), and optional **full-text PDF parsing**
(`pip install paperpulse[pdf]`) so several of the above can read past the abstract.

## Region tagging and the known/already-tried factor log

Every digest entry gets a keyword-detected **region tag** (USA / EUR / CHN / IND /
Global-Unspecified) from index and market names in the abstract, and you can
filter to specific regions with `region_filter` in config.

A shared SQLite log (`topics_db`) tracks factor families you or the literature
already know about:

```bash
paperpulse factors add "board diversity" --aliases "board gender diversity" \
  --source manual --result dead --notes "tried 6 variants, no edge"
paperpulse factors list
paperpulse factors check   # today's digest, but only "new evidence" on tracked dead/weak factors
```

A paper matching a `dead`/`weak` entry gets a hard 🔴 flag with your own notes
attached; a `promising` entry surfaces as a positive note instead of a caution.
If `already_tested_regions` says you've only tested a factor in the USA, the
same factor showing up in a paper about India gets a green "untested region —
may still be valid to explore" note rather than being suppressed.

## Beyond the digest

- **Multiple sources** — arXiv, bioRxiv/medRxiv, PubMed, and SSRN (via OpenAlex, not a
  direct scraper) behind one interface (`paperpulse run --source ssrn`). Adding
  OpenReview is one adapter.
- **Contradiction mapping** — surfaces pairs of closely-related papers that report opposing outcomes.
- **Cross-reference your own work** — `paperpulse similar my_model.py` finds papers whose methods are functionally closest to your code or notebook.
- **Market context for finance papers** — when a paper names a well-known asset (an index, crypto, commodity, or mega-cap), the dashboard tags it with the latest price from Yahoo Finance so you can sanity-check a claim at a glance. Stdlib-only, no API key.
- **Per-paper notes** — `paperpulse note <id> "text"` keeps a running annotation log per paper (needs `community_db`).
- **Delivery anywhere** — Markdown file, email (SMTP), RSS feed, or Slack/Discord webhook.
- **Community trust store** — a self-hostable SQLite DB that pools trust reports across users and builds an over-claiming leaderboard.
- **Dashboard filter presets** — one-click "Region: USA only", "Known factor families only",
  "Untested regions only" in the web dashboard.

## Three ways to use it

```bash
# 1. CLI
paperpulse run --source arxiv --categories cs.LG cs.CL

# 2. Python SDK
python -c "from paperpulse.pipeline import run_digest; from paperpulse.config import Config; \
           print(run_digest(Config(), dry_run=True).markdown)"

# 3. REST API + web dashboard (stdlib only, no extra deps)
paperpulse serve            # http://127.0.0.1:8000
#   Interactive topic-filter bar (Finance / Economics / Quant), loads instantly,
#   with live price chips on any paper that names a major asset.
#   GET /api/digest?cats=q-fin.TR,econ.GN   POST /api/feedback   GET /api/community/leaderboard
```

Or with Docker:

```bash
docker compose up          # dashboard on :8000, state persisted in a volume
```

## Configuration

`paperpulse init` writes a commented `paperpulse.yaml`
(see [`paperpulse.example.yaml`](paperpulse.example.yaml)). Everything is
config-driven: sources, categories, which trust signals to enable, ranking
diversity, delivery, `avoid_topics`, `region_filter`, and `topics_db`.

Secrets are read from the environment, never the config file:
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (LLM summaries), `PAPERPULSE_SMTP_*`
(email), `PAPERPULSE_SLACK_WEBHOOK` / `PAPERPULSE_DISCORD_WEBHOOK`, `NCBI_API_KEY`.

## Scheduling

Run it daily with cron, or use the included GitHub Action
([`.github/workflows/digest.yml`](.github/workflows/digest.yml)) to generate and
commit a digest every weekday morning.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The full test suite is offline — no network, no keys — so it runs anywhere.

See [`ROADMAP.md`](ROADMAP.md) for what's shipped and what's next.

### Publishing

`pip install build twine && python -m build && twine check dist/*` builds and
validates the wheel. Cutting a **GitHub Release** then publishes it to PyPI via
[`release.yml`](.github/workflows/release.yml) (Trusted Publishing — no token in
the repo; add the publisher once on PyPI first). Or push manually with
`twine upload dist/*`.

## License

MIT — see [`LICENSE`](LICENSE).
