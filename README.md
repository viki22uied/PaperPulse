# PaperPulse

[![CI](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperpulse)](https://pypi.org/project/paperpulse/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Every day, arXiv posts hundreds of new papers. PaperPulse picks the five that actually matter to you, tells you whether to trust them, and explains why — all in plain English.**

📄 **[See a real digest generated today →](examples/2026-07-14.md)** &nbsp;·&nbsp;
🗺️ **[Roadmap](ROADMAP.md)** &nbsp;·&nbsp;
🧪 **[Annotated example](examples/sample-digest.md)**

## What it actually does

1. **Ranks papers by what you care about.** You describe your interests in a sentence. PaperPulse ranks today's papers against that, and gets smarter every time you say "more like this" / "less like this."
2. **Flags papers that look shaky.** No error bars, no code, hyped-up language, results that only hold on one dataset — PaperPulse scans for the patterns that usually mean weaker work, and shows you exactly which words triggered the flag.
3. **Remembers what you've already ruled out.** Log a topic as "dead end, already tried" once, and PaperPulse will flag it every time it resurfaces — even in a different country's market or a different dataset.

No API keys, no paid services, no sign-up. It works offline out of the box.

```bash
pip install paperpulse
paperpulse init      # 30-second setup wizard
paperpulse run       # today's digest -> digests/YYYY-MM-DD.md
```

## Finance papers get an extra "alpha card"

If a paper claims to find a trading edge, PaperPulse pulls out the specifics: what it's predicting, what data it used, what numbers it reported, and over what time period. A card can be:

- **Strong** — data, numbers, and dates are all there. You could try to reproduce it.
- **Vague** — the paper talks about markets but gives you nothing to check. This is the important case: it looks credible until you notice there's nothing underneath.

```bash
paperpulse alpha                       # today's papers as alpha cards
paperpulse alpha --full-text           # also reads the actual PDF, not just the abstract (needs: pip install "paperpulse[pdf]")
```

### The options-backtest demo — read this before you install it

`paperpulse backtest` is a **teaching tool, not a trading tool.** It runs a real backtesting engine ([optopsy](https://github.com/goldspanlabs/optopsy)) on made-up, synthetic data, so you can see how an options strategy is actually tested — how strikes get picked, what a win/loss report looks like, why even a "good" strategy loses money sometimes.

It does **not**:
- verify whether any paper's claim is true
- use real market data
- connect to a broker or place any trade
- give you financial advice of any kind

Think of it as a flight simulator for reading finance papers, not an autopilot. It's an optional extra (`pip install "paperpulse[backtest]"`, needs Python 3.12+) — it's off by default and the rest of PaperPulse doesn't need it.

## Using it

```bash
# Command line
paperpulse run --categories cs.LG cs.CL

# As a Python library
python -c "from paperpulse.pipeline import run_digest; from paperpulse.config import Config; \
           print(run_digest(Config(), dry_run=True).markdown)"

# Web dashboard (built in, no extra install)
paperpulse serve            # open http://127.0.0.1:8000
```

The dashboard has clickable topic filters, a settings panel to change what you're tracking without touching a config file, and renders any math in an abstract properly instead of showing raw symbols.

Or with Docker: `docker compose up`

## Why not just ask an LLM to summarize arXiv?

| | Typical "arXiv + LLM" script | PaperPulse |
|---|---|---|
| Ranking | Newest first | Ranked by *your* interests, and gets better as you give feedback |
| Trust | Trusts whatever the summary says | 15+ automated checks for weak/shaky work, each one explained |
| Memory | None — sees the same thing every day | Remembers what you've already ruled out |
| Cost | Needs an API key | Runs fully offline for free |

## More features

- **Multiple sources** — arXiv, bioRxiv, medRxiv, PubMed, SSRN
- **Finds contradictions** — flags pairs of recent papers that disagree with each other
- **Compares to your own code** — `paperpulse similar my_model.py` finds papers closest to what you're already working on
- **Live prices for finance papers** — if a paper mentions the S&P 500, Bitcoin, etc., the dashboard shows the current price next to it (no API key needed)
- **Notes** — jot down your own thoughts against any paper and keep them
- **Delivery** — save to a file, email, RSS feed, or post to Slack/Discord
- **Shared trust database** — a team can pool their trust scores in one place

## Configuration

`paperpulse init` writes a `paperpulse.yaml` you can edit by hand — see [`paperpulse.example.yaml`](paperpulse.example.yaml) for every option, commented.

API keys and passwords always go in environment variables, never in the config file: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (only needed if you want AI-written summaries instead of the free built-in ones), `PAPERPULSE_SMTP_*` (email), `PAPERPULSE_SLACK_WEBHOOK` / `PAPERPULSE_DISCORD_WEBHOOK`, `NCBI_API_KEY`, `PAPERPULSE_API_TOKEN` (protects the dashboard if you put it on a shared server).

## Scheduling

Run it daily with cron, or use the included GitHub Action to generate and commit a digest every weekday morning ([`.github/workflows/digest.yml`](.github/workflows/digest.yml)).

## Contributing

```bash
pip install -e ".[dev]"
pytest
```

Tests run fully offline — no network, no API keys required. See [`ROADMAP.md`](ROADMAP.md) for what's built and what's planned.

## License

MIT — see [`LICENSE`](LICENSE).
