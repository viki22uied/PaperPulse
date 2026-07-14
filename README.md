# PaperPulse

**The five papers that actually matter to you today — ranked, trust-scored, and summarised in plain English.**

arXiv drops hundreds of papers a day. Summaries are a solved problem; *triage*
isn't. PaperPulse is built around the two questions that actually waste your
time:

1. **Which of today's 200 papers are relevant to *me*?** — a learnable interest
   profile ranks every abstract by similarity to what you care about, and a
   thumbs-up/down feedback loop sharpens it over time.
2. **Which of those should I actually trust?** — a set of offline *signal-quality*
   heuristics flag over-claiming, missing error bars, weak baselines, likely data
   leakage, benchmark-chasing, and incremental "me-too" work, before you sink
   twenty minutes into the PDF.

It runs out of the box with **no API keys and no model downloads** (local hashing
embeddings + extractive summaries), and scales up cleanly to semantic embeddings
and LLM summaries when you want them.

```bash
pip install -e .
paperpulse init          # write a starter paperpulse.yaml
# edit `interests` and `categories`
paperpulse run           # today's ranked, trust-scored digest -> digests/YYYY-MM-DD.md
```

👉 **[See a sample digest](examples/sample-digest.md)** — note how the finance
paper gets a 🚩 *leakage* flag and the hype paper collects four flags while a
careful LoRA study rises to the top.

---

## Why it's not just another arXiv scraper

| | Typical "arXiv + LLM" script | PaperPulse |
|---|---|---|
| Ranking | none / recency | learnable interest vector + **MMR diversity** |
| Personalisation | static keywords | **Rocchio feedback loop**, per-user profiles |
| Trust | blind trust in the summary | **10+ signal-quality checks** with a badge |
| Novelty | — | **crowding score** flags incremental work |
| Provenance | — | every summary line traces back to a source sentence |
| Cost to start | API key required | **runs fully offline** |

## How the ranking works

1. **Embed** each abstract into a stable vector space. The default
   `HashingBackend` needs no model and no training, so a profile learned today is
   still comparable next week. Install `paperpulse[semantic]` to switch to
   sentence-transformers for sharper semantics — same interface, better vectors.
2. **Score** by cosine similarity to your interest vector.
3. **Select** the top *N* with **Maximal Marginal Relevance**, trading a little
   relevance for variety so you don't get five near-identical papers.
4. **Learn.** `paperpulse feedback --like 2407.00004 --dislike 2407.00002`
   nudges the profile toward what you liked and away from what you didn't
   (Rocchio), anchored so it never drifts far from the interests you wrote down.

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
- **subgroup robustness** — do strong aggregate numbers hide weak subgroups?
- **metric gaming** — did a metric move without a genuine underlying gain?
- **deployability** — oracle inputs, look-ahead features, or unrealistic compute?
- **leakage** — random splits on time-series/financial data (a classic lookahead trap)
- **baseline fairness**, **evidence / error bars**, **over-claiming**, **benchmark saturation**, **reproducibility (code/data links)**

Turn on `--online` (or `trust_online: true`) to add **dead-link detection**, a
**Retraction Watch** cross-check, and a **self-citation ratio** (via Semantic
Scholar — set `S2_API_KEY` for higher rate limits).

## Beyond the digest

- **Multiple sources** — arXiv, bioRxiv/medRxiv, and PubMed behind one interface (`paperpulse run --source pubmed`). Adding OpenReview/SSRN is one adapter.
- **Contradiction mapping** — surfaces pairs of closely-related papers that report opposing outcomes, and a "what changed since last week" diff for a tracked subfield.
- **Cross-reference your own work** — `paperpulse similar my_model.py` finds papers whose methods are functionally closest to your code or notebook.
- **Market context for finance papers** — when a paper names a well-known asset (an index, crypto, commodity, or mega-cap), the dashboard tags it with the latest price from Yahoo Finance so you can sanity-check a claim at a glance. Stdlib-only, no API key.
- **Full-text PDF parsing** (`paperpulse[pdf]`) for sharper trust signals and provenance.
- **Delivery anywhere** — Markdown file, email (SMTP), RSS feed, or Slack/Discord webhook.
- **Community trust store** — a self-hostable SQLite DB that pools trust reports across users, supports PubPeer-style annotations, and builds an over-claiming leaderboard.

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
diversity, and delivery.

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

## License

MIT — see [`LICENSE`](LICENSE).
