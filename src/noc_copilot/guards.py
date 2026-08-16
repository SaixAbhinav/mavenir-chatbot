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
    """Compare quotes ignoring whitespace and case, nothing else.

    Tolerating whitespace costs nothing in strictness — a model that reformats a
    tab is not inventing a claim — and the real fabrication this gate exists to
    catch (findings §4.23) fails the comparison either way.
    """
    return _WHITESPACE.sub(" ", text).strip().lower()


def gate_relevance(hits, settings: Settings) -> str | None:
    """Thresholds RAW scores. Never RRF — fused ranks carry no absolute relevance.

    Reads ranked Hits only. A Hit added by sibling expansion is in the context
    because a neighbour scored well, so counting its scores here would let a
    sibling rescue a retrieval that found nothing.

    Note this gate cannot carry the out-of-scope refusal rate on its own: the
    raw cosine of an answerable question and of an in-domain but out-of-corpus
    one overlap almost completely (findings §4.18). It is a coarse filter; Gates
    2 and 3 do the discriminating work.
    """
    ranked = [h for h in hits if not h.expanded]
    if not ranked:
        return NO_RELEVANT_CLAUSE
    if settings.cosine_threshold is None or settings.bm25_threshold is None:
        return None  # uncalibrated: gate is inactive until Task 16
    best_cosine = max(h.cosine for h in ranked)
    best_bm25 = max(h.bm25 for h in ranked)
    # Either signal alone is enough: BM25 carries exact identifiers that dense
    # similarity blurs, and dense carries paraphrases that BM25 misses.
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
    # One clause id can span several Chunks, because an oversized clause is
    # split. Keep every part: a quote may come from any of them.
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
