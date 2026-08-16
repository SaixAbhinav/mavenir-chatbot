"""The three Gates. All deterministic, all outside the model.

Gate 1 catches "nothing in the corpus is about this".
Gate 2 catches "on-topic clauses that lack the specific fact".
Gate 3 catches fabricated clause ids and claims not anchored to real text.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .config import Settings
from .schemas import Answer

NO_RELEVANT_CLAUSE = "no_relevant_clause"
INSUFFICIENT = "insufficient"
NOT_ANSWERABLE_FROM_STANDARDS = "not_answerable_from_standards"
UNVERIFIABLE = "unverifiable"

_WHITESPACE = re.compile(r"\s+")


def normalise_quote(text: str) -> str:
    """Normalise a quote for comparison: collapse whitespace, lowercase.
    Reformatting isn't fabrication; the claims this catches fail either way."""
    return _WHITESPACE.sub(" ", text).strip().lower()


def gate_relevance(hits, settings: Settings) -> str | None:
    """Threshold RAW cosine/BM25 (never RRF — fused ranks carry no absolute
    relevance), reading ranked Hits only. A coarse filter; Gates 2 and 3 do the
    discriminating work."""
    ranked = [h for h in hits if not h.expanded]
    if not ranked:
        return NO_RELEVANT_CLAUSE
    if settings.cosine_threshold is None or settings.bm25_threshold is None:
        return None  # uncalibrated: gate is inactive until thresholds are set
    best_cosine = max(h.cosine for h in ranked)
    best_bm25 = max(h.bm25 for h in ranked)
    # Either signal alone suffices: BM25 catches exact ids, dense catches paraphrases.
    if best_cosine < settings.cosine_threshold and best_bm25 < settings.bm25_threshold:
        return NO_RELEVANT_CLAUSE
    return None


def gate_sufficiency(answer: Answer) -> str | None:
    if not answer.answerable_from_standards:
        return NOT_ANSWERABLE_FROM_STANDARDS
    if not answer.sufficient:
        return INSUFFICIENT
    return None


def gate_verifiability(answer: Answer, hits) -> str | None:
    if not answer.citations:
        return UNVERIFIABLE
    # One clause id can span several Chunks (split clause); keep every part.
    by_clause: dict[str, list[str]] = defaultdict(list)
    for h in hits:
        by_clause[h.clause_id].append(normalise_quote(h.text))
    for citation in answer.citations:
        parts = by_clause.get(citation.clause_id)
        if not parts:
            return UNVERIFIABLE
        quote = normalise_quote(citation.supporting_quote)
        if not any(quote in part for part in parts):
            return UNVERIFIABLE
    return None
