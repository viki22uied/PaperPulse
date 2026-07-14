"""Summarisation.

Summarising an abstract is the easy part, so we don't require an LLM for it.
The default extractive summariser picks the most representative sentences and
runs everywhere. If you set ``OPENAI_API_KEY`` (or ``ANTHROPIC_API_KEY``) and
enable it in config, you get a tighter three-bullet "problem / method / result"
digest instead.
"""

from __future__ import annotations

import os
import re

from .models import Paper

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_PROMPT = (
    "Summarise this paper abstract for a busy researcher in exactly three "
    "short bullet points, in plain English:\n"
    "- Problem: what gap or question it addresses\n"
    "- Method: what they actually did\n"
    "- Result: the key finding and why it matters\n\n"
    "Title: {title}\n\nAbstract: {abstract}"
)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def extractive_summary(paper: Paper, max_sentences: int = 3) -> str:
    """Score sentences by lexical overlap with the abstract as a whole and
    keep the top few, preserving their original order.

    Simple, deterministic, and offline -- a reasonable default that never
    silently costs money or leaks the abstract to a third party.
    """
    sentences = _split_sentences(paper.abstract)
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    def tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    doc = tokens(paper.abstract)
    scored = []
    for idx, sentence in enumerate(sentences):
        words = tokens(sentence)
        overlap = len(words & doc) / (len(words) + 1)
        # A gentle nudge toward earlier sentences, which usually frame the work.
        position_bonus = 1.0 / (1 + idx * 0.15)
        scored.append((overlap * position_bonus, idx, sentence))

    top = sorted(scored, reverse=True)[:max_sentences]
    top.sort(key=lambda item: item[1])
    return " ".join(sentence for _, _, sentence in top)


def _llm_summary(paper: Paper) -> str | None:
    prompt = _PROMPT.format(title=paper.title, abstract=paper.abstract)

    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model=os.getenv("PAPERPULSE_OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return None

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=os.getenv("PAPERPULSE_ANTHROPIC_MODEL", "claude-sonnet-5"),
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in resp.content if block.type == "text"
            ).strip()
        except Exception:
            return None

    return None


def summarise(paper: Paper, use_llm: bool = False, max_sentences: int = 3) -> str:
    """Summarise a paper, falling back to the extractive summary whenever the
    LLM path is disabled or unavailable."""
    if use_llm:
        result = _llm_summary(paper)
        if result:
            return result
    return extractive_summary(paper, max_sentences=max_sentences)
