# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- arXiv client `User-Agent` now reports the real package version instead of a
  hardcoded `0.1`.
- The digest cache uses one lock per category key, so requests for different
  topic filters no longer serialize behind each other. Concurrent requests for
  the *same* filter still collapse into a single arXiv fetch.

- The package version is now declared once, in `paperpulse/__init__.py`, and
  read from there by setuptools via `dynamic = ["version"]`. Previously it was
  duplicated in `pyproject.toml` and could drift.

### Added
- `mypy` runs in CI across the supported Python versions.

## [0.2.0] - 2026-07-16

### Added
- **Relevance ranking** — a learnable interest profile scores every abstract by
  similarity to what you care about, with a thumbs-up/down feedback loop and an
  `avoid_topics` list that ranks down factor families you've worked to death.
- **Trust layer** — offline signal-quality heuristics flag over-claiming, missing
  error bars, weak baselines, likely data leakage, benchmark-chasing, weak/null
  results, and incremental "me-too" work, each with evidence and a confidence.
- **Known-factor / already-tried log** — flags papers matching something you or
  the literature already found dead, weak, or crowded, and green-lights the same
  factor in a region you haven't tested yet.
- **Community DB** — shared notes and a flag leaderboard over SQLite.
- **REST API and dashboard** — `paperpulse serve` exposes `/api/digest`,
  `/api/feedback`, `/api/notes`, and `/api/community/leaderboard`, plus a
  filterable web dashboard with live price chips. Standard library only.
- **Multi-source ingestion** — pluggable sources with arXiv and SSRN adapters.
- **Region tagging** — surfaces which markets a paper's evidence covers.

### Fixed
- `known_topic` no longer treats "promising" the same as "untested".
- `created_at` is preserved when re-logging an existing topic.
- UTF-8 encoding crashes on non-UTF-8 consoles and locales.

[Unreleased]: https://github.com/viki22uied/PaperPulse/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/viki22uied/PaperPulse/releases/tag/v0.2.0
