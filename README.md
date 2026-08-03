# PaperPulse

[![CI](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/viki22uied/PaperPulse/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/paperpulse)](https://pypi.org/project/paperpulse/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/viki22uied/PaperPulse?style=social)](https://github.com/viki22uied/PaperPulse/stargazers)

**Each day, arXiv publishes hundreds of new papers. PaperPulse selects the five most relevant papers for you. It checks their quality and tells you why each paper matters.**

If this tool saves you time, a star helps other researchers find it.

[See a real digest](examples/2026-07-31.md) | [Roadmap](ROADMAP.md) | [Annotated example](examples/sample-digest.md)

![PaperPulse dashboard — ranked papers with trust scores, relevance bars, badges, and alpha cards](docs/screenshot.png)

## What PaperPulse Does

1. **Ranks papers by your interests.** You describe your research interests in one sentence. PaperPulse ranks each new paper against your profile. The ranking improves each time you give feedback.
2. **Flags weak papers.** PaperPulse scans for missing error bars, missing code, exaggerated language, and single-dataset results. It shows you the exact words that caused each flag.
3. **Tracks topics you already tested.** Log a topic as "dead end" once. PaperPulse flags that topic each time it appears again, even in a different market or dataset.

PaperPulse does not need API keys, paid services, or sign-up. It works fully offline.

```bash
pip install paperpulse
paperpulse init      # 30-second setup
paperpulse run       # makes today's digest in digests/YYYY-MM-DD.md
```

## Alpha Cards for Finance Papers

PaperPulse extracts testable claims from finance papers. Each alpha card shows the predictor, the target, the data sources, the effect sizes, and the time period.

- **Strong** — The paper gives data, numbers, and dates. You can try to reproduce the result.
- **Vague** — The paper discusses markets but gives no data to check.

```bash
paperpulse alpha                       # show alpha cards for today's papers
paperpulse alpha --full-text           # also read the PDF (needs: pip install "paperpulse[pdf]")
```

## How to Use PaperPulse

```bash
# Run from the command line
paperpulse run --categories cs.LG cs.CL

# Get structured JSON output
paperpulse run --format json | jq '.papers[] | select(.trust.badge == "clean")'

# Export to your reference manager
paperpulse export -o today.bib      # BibTeX for Zotero, Mendeley, EndNote, LaTeX

# Use as a Python library
python -c "from paperpulse.pipeline import run_digest; from paperpulse.config import Config; \
           print(run_digest(Config(), dry_run=True).markdown)"

# Start the web dashboard
paperpulse serve            # open http://127.0.0.1:8000
```

The dashboard has topic filters, a settings panel, and renders LaTeX math correctly. You can also start with Docker: `docker compose up`

## PaperPulse Compared to LLM Scripts

| Feature | Typical arXiv + LLM script | PaperPulse |
|---|---|---|
| Ranking | Shows newest papers first | Ranks papers by your interests. Improves with feedback |
| Trust | Trusts the summary text | Runs 15+ automated checks. Explains each flag |
| Memory | No memory between runs | Remembers topics you already tested |
| Cost | Needs an API key | Runs fully offline at no cost |

## More Features

- **Multiple sources** — arXiv, bioRxiv, medRxiv, PubMed, SSRN
- **Contradiction detection** — Flags pairs of papers that disagree. Shows what changed this week
- **BibTeX export** — `paperpulse export` creates entries for Zotero, Mendeley, EndNote, or LaTeX
- **JSON output** — `paperpulse run --format json` for scripts and dashboards
- **Code comparison** — `paperpulse similar my_model.py` finds papers close to your code
- **Live prices** — The dashboard shows current prices when a paper mentions S&P 500, Bitcoin, or other assets
- **Notes** — Save your own notes on any paper
- **Delivery** — Save to a file, send by email, publish as RSS, or post to Slack/Discord
- **Shared trust database** — A team can pool trust scores and measure badge accuracy (`paperpulse score-accuracy`)
- **Flag-validation ledger** — Records every trust flag at assessment time. Reconciles flags against ground-truth outcomes: retraction (Crossref/OpenAlex), citation decline, and out-of-sample decay (Chen-Zimmermann data). Reports per-badge Brier scores and lift over the base rate (`paperpulse reconcile`, `paperpulse calibration`)
- **Overfitting screener** — Flags t-stats below the Harvey-Liu factor-zoo hurdle (3.0). Flags Sharpe ratios without trial counts (Deflated Sharpe Ratio gap). Flags missing out-of-sample validation
- **Polarity-flip monitor** — Tracks contradiction pairs over time. Alerts you when a pair changes direction. Reports per-pair consensus volatility (`paperpulse polarity`)
- **Flag-survival benchmark** — Tracks per-signal precision against realized outcomes. Shows which flags predict real problems (`paperpulse flag-survival`)

## Configuration

Run `paperpulse init` to create a `paperpulse.yaml` file. You can edit this file manually. See [`paperpulse.example.yaml`](paperpulse.example.yaml) for all options.

Put API keys and passwords in environment variables. Do not put them in the config file.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | AI summaries (optional; built-in summaries work without these) |
| `PAPERPULSE_SMTP_*` | Email delivery |
| `PAPERPULSE_SLACK_WEBHOOK` / `PAPERPULSE_DISCORD_WEBHOOK` | Chat delivery |
| `NCBI_API_KEY` | PubMed access (optional) |
| `PAPERPULSE_API_TOKEN` | Guards all API and dashboard routes when set |

### Security

- All outbound requests go through a no-redirect opener. An approved host cannot redirect the request to an unapproved host.
- All SQLite queries use parameterized statements. Config files load through `yaml.safe_load`.
- `PAPERPULSE_API_TOKEN` guards every route except the static dashboard page.
- If you find a security problem, open an issue. Do not put exploit details in a public pull request.

## Scheduling

Run PaperPulse daily with cron. You can also use the included GitHub Action to create a digest every weekday morning. See [`.github/workflows/digest.yml`](.github/workflows/digest.yml).

## Built with AI

I developed the features, tests, and research for this project with the help of AI (Claude). The domain logic comes from my own research background. This includes the selection of academic frameworks (Harvey-Liu, DSR/PBO, Chen-Zimmermann) and the design of each signal. AI accelerated the implementation, the stress-testing, and the iteration cycle.

## How to Contribute

```bash
pip install -e ".[dev]"
pytest
```

All tests run fully offline. No network access or API keys are necessary. See [`ROADMAP.md`](ROADMAP.md) for the full status of each feature.

## License

MIT — see [`LICENSE`](LICENSE).
