"""Weak/null-result detection (A3).

A genuinely novel-sounding paper can still report a weak or null finding --
that's a property of the *result*, not the methodology, so it gets its own
badge rather than folding into the general trust signals. Pattern-matching on
"no significant" etc. is prone to one specific false positive: a sentence that
uses the same words in a *positive* framing ("no significant difference across
subgroups, confirming robustness"). ``_OVERRIDE`` catches that case in the same
sentence and suppresses the flag.
"""

from __future__ import annotations

import re

from ..models import Paper
from . import OK, WARN, Signal, signal

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

WEAK_RESULT_TERMS = re.compile(
    r"\b(no significant\w*|mixed results?|inconclusive|"
    r"small effect|not robust|fails? to replicate|null result|"
    r"no evidence of (?:an? )?(?:effect|improvement|gain)|"
    r"weak(?:\W+\w+){0,4}\W+evidence|evidence(?:\W+\w+){0,4}\W+weak)\b",
    re.I,
)

# A weak-result phrase inside a sentence that also says this, is a positive
# framing ("no significant difference ... confirming robustness"), not a flag.
# The negative lookbehind keeps "not robust" (an actual weak-result claim)
# from being swallowed by its own override term.
_OVERRIDE = re.compile(
    r"\b(confirm\w*|consistent with|(?<!not )robust\w*|as expected|"
    r"support\w* (?:the|our) (?:hypothesis|finding)|"
    r"no evidence of (?:overfitting|leakage|bias|confound\w*))\b",
    re.I,
)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


@signal("weak_result")
def weak_result_signal(paper: Paper, *, full_text: str | None = None, **_) -> Signal:
    """Flag weak/null-result language. Prefers scanning full-text results /
    discussion sections when available, since abstracts tend to overstate
    findings relative to the body."""
    text = full_text if full_text else paper.abstract
    for sentence in _split_sentences(text):
        match = WEAK_RESULT_TERMS.search(sentence)
        if match and not _OVERRIDE.search(sentence):
            return Signal(
                "weak_result",
                WARN,
                "Possible weak/null result -- verify: " + sentence.strip(),
                evidence=sentence.strip(),
                confidence=0.5,
            )
    return Signal("weak_result", OK, "No weak/null-result language detected.")


__all__ = ["weak_result_signal"]
