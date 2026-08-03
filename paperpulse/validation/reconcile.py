"""Ground-truth reconcilers: pull real outcomes and attach them to the ledger.

Each reconciler queries a public data source, matches papers by DOI or arXiv
id, and records outcomes for any match found.  All fail soft: a network
timeout or API error skips that paper, never crashes the run.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from ..netguard import NO_REDIRECT_OPENER
from .ledger import ValidationLedger


class Reconciler(Protocol):
    def run(self, ledger: ValidationLedger) -> list[dict]: ...


@dataclass
class _OutcomeHit:
    paper_id: str
    outcome: str
    source: str
    detail: str = ""


def _safe_get(url: str, timeout: float = 20.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "PaperPulse/0.5"})
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


class RetractionReconciler:
    """Check flagged papers against Crossref's retraction metadata.

    Uses the Crossref REST API with ``filter=update-type:retraction`` and
    the OpenAlex ``is_retracted`` flag as a fallback -- both are free,
    DOI-joinable, and need no API key.
    """

    CROSSREF_API = "https://api.crossref.org/works/{doi}"
    OPENALEX_API = "https://api.openalex.org/works/doi:{doi}"

    def run(self, ledger: ValidationLedger) -> list[dict]:
        dois = ledger.dois()
        if not dois:
            return []

        hits: list[dict] = []
        for paper_id, doi in dois.items():
            if not doi:
                continue
            retracted, source, detail = self._check(doi)
            if retracted:
                if ledger.record_outcome(
                    paper_id, outcome="retracted", source=source, detail=detail
                ):
                    hits.append({
                        "paper_id": paper_id,
                        "doi": doi,
                        "outcome": "retracted",
                        "source": source,
                    })
        return hits

    def _check(self, doi: str) -> tuple[bool, str, str]:
        retracted, source, detail = self._check_crossref(doi)
        if retracted:
            return True, source, detail
        return self._check_openalex(doi)

    def _check_crossref(self, doi: str) -> tuple[bool, str, str]:
        url = self.CROSSREF_API.format(doi=urllib.parse.quote(doi, safe=""))
        data = _safe_get(url)
        if data is None:
            return False, "", ""
        try:
            work = json.loads(data).get("message", {})
        except (json.JSONDecodeError, AttributeError):
            return False, "", ""
        updates = work.get("update-to", [])
        for u in updates:
            if u.get("type") == "retraction" or u.get("label", "").lower() == "retraction":
                return True, "crossref", json.dumps(u, default=str)
        return False, "", ""

    def _check_openalex(self, doi: str) -> tuple[bool, str, str]:
        url = self.OPENALEX_API.format(doi=urllib.parse.quote(doi, safe=""))
        data = _safe_get(url)
        if data is None:
            return False, "", ""
        try:
            record = json.loads(data)
        except (json.JSONDecodeError, AttributeError):
            return False, "", ""
        if record.get("is_retracted"):
            return True, "openalex", ""
        return False, "", ""


class ReplicationReconciler:
    """Match papers against known replication databases.

    Currently checks OpenAlex for citation-context signals (contrasting
    citations as a weak proxy for replication failure).  Extensible to
    FORRT/FLoRA once a stable API endpoint is available.
    """

    OPENALEX_CITED_BY = (
        "https://api.openalex.org/works?filter=cites:{work_id}"
        "&per_page=50&select=id,cited_by_count,is_retracted"
    )
    OPENALEX_WORK = "https://api.openalex.org/works/doi:{doi}"

    def run(self, ledger: ValidationLedger) -> list[dict]:
        dois = ledger.dois()
        hits: list[dict] = []
        for paper_id, doi in dois.items():
            if not doi:
                continue
            result = self._check(doi)
            if result:
                if ledger.record_outcome(
                    paper_id,
                    outcome=result["outcome"],
                    source="openalex_citations",
                    detail=result.get("detail", ""),
                ):
                    hits.append({"paper_id": paper_id, **result})
        return hits

    def _check(self, doi: str) -> dict | None:
        work_url = self.OPENALEX_WORK.format(doi=urllib.parse.quote(doi, safe=""))
        data = _safe_get(work_url)
        if data is None:
            return None
        try:
            work = json.loads(data)
        except (json.JSONDecodeError, AttributeError):
            return None

        work_id = work.get("id", "")
        if not work_id:
            return None

        cited_count = work.get("cited_by_count", 0)
        if cited_count == 0:
            return None

        counts = work.get("counts_by_year", [])
        if len(counts) >= 3:
            recent = sum(c.get("cited_by_count", 0) for c in counts[:2])
            older = sum(c.get("cited_by_count", 0) for c in counts[2:4])
            if older > 10 and recent < older * 0.2:
                return {
                    "outcome": "citation_decline",
                    "detail": f"Citations dropped from {older} to {recent} (recent vs older 2yr windows)",
                }
        return None


class FinanceDecayReconciler:
    """Check alpha-card papers against known out-of-sample decay.

    Uses the Chen-Zimmermann Open Source Asset Pricing data to check whether
    a paper's claimed anomaly shows post-publication decay.  The reconciler
    matches by arXiv-extracted factor names against the CZ characteristic
    catalog and flags significant t-stat declines.

    This is a local-data reconciler: it reads a CZ summary CSV if present
    at the configured path, no network call needed.
    """

    def __init__(self, cz_data_path: str = ""):
        self.cz_data_path = cz_data_path
        self._catalog: dict[str, dict] | None = None

    def _load_catalog(self) -> dict[str, dict]:
        if self._catalog is not None:
            return self._catalog
        if not self.cz_data_path:
            self._catalog = {}
            return self._catalog
        import csv
        from pathlib import Path

        path = Path(self.cz_data_path)
        if not path.exists():
            self._catalog = {}
            return self._catalog

        catalog: dict[str, dict] = {}
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("signalname", "").strip().lower()
                if name:
                    catalog[name] = {
                        "original_tstat": _float(row.get("tstat_original", "")),
                        "replicated_tstat": _float(row.get("tstat_replicated", "")),
                        "post_pub_tstat": _float(row.get("tstat_postpub", "")),
                        "authors": row.get("authors", ""),
                        "year": row.get("year", ""),
                    }
        self._catalog = catalog
        return self._catalog

    def run(self, ledger: ValidationLedger) -> list[dict]:
        catalog = self._load_catalog()
        if not catalog:
            return []

        hits: list[dict] = []
        for paper_id in ledger.all_paper_ids():
            flags = ledger.flags_for(paper_id)
            factor_names = self._extract_factor_names(flags)
            for name in factor_names:
                key = name.lower().replace("-", "_").replace(" ", "_")
                entry = catalog.get(key)
                if entry is None:
                    continue
                orig = entry.get("original_tstat")
                post = entry.get("post_pub_tstat")
                if orig is not None and post is not None and orig > 0:
                    decay = 1.0 - (post / orig)
                    if decay > 0.3:
                        detail = (
                            f"t-stat decayed {decay:.0%} post-publication "
                            f"(original {orig:.2f} -> post-pub {post:.2f})"
                        )
                        if ledger.record_outcome(
                            paper_id,
                            outcome="oos_decay",
                            source="chen_zimmermann",
                            detail=detail,
                        ):
                            hits.append({
                                "paper_id": paper_id,
                                "factor": name,
                                "outcome": "oos_decay",
                                "detail": detail,
                            })
        return hits

    @staticmethod
    def _extract_factor_names(flags: list[dict]) -> list[str]:
        names = []
        for f in flags:
            ev = f.get("evidence", "")
            if ev:
                names.append(ev.split("(")[0].strip())
        return [n for n in names if n]


def _float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
