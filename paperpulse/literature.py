"""Reference set of well-known asset-pricing factor papers, for the
"novelty vs known literature" check (E2).

The existing ``crowding`` signal only compares a paper to others in *today's*
batch. This compares it against a small, fixed set of canonical factor papers
(plus anything logged in the shared known/tried topics store) independent of
what else arrived today -- catching "this is just Fama-French value again"
even when nothing else in the batch is similar.

A plain Python list, not a config-loaded data file: it almost never changes,
so a maintained YAML with its own loader would be an abstraction with no
second caller.
"""

from __future__ import annotations

CANONICAL_FACTOR_PAPERS: list[str] = [
    "Fama French three factor model: market, size (small minus big), and "
    "value (high minus low book-to-market) explain the cross-section of "
    "stock returns.",
    "Carhart four factor model adds a momentum factor (up minus down, "
    "based on prior 12-month returns) to the Fama-French three factors.",
    "Fama French five factor model adds profitability (robust minus weak) "
    "and investment (conservative minus aggressive) factors to size and value.",
    "Jegadeesh Titman momentum: stocks with high returns over the past 3 to "
    "12 months continue to outperform stocks with low past returns.",
    "Frazzini Pedersen betting against beta: low-beta assets have higher "
    "risk-adjusted returns than high-beta assets, a leveraged low-volatility "
    "anomaly.",
    "Asness Frazzini Pedersen quality minus junk: high-quality stocks -- "
    "profitable, growing, safe, well-managed -- earn higher risk-adjusted "
    "returns than low-quality stocks.",
    "Novy-Marx gross profitability premium: firms with high gross profits "
    "relative to assets earn higher average returns, a profitability factor "
    "distinct from value.",
    "Ang Hodrick Xing Zhang low volatility anomaly: stocks with high "
    "idiosyncratic volatility earn abysmally low average returns.",
]

__all__ = ["CANONICAL_FACTOR_PAPERS"]
