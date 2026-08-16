"""Retrieve -> Gate 1 -> generate -> Gate 2 -> Gate 3."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .generate import generate
from .guards import (
    UNVERIFIABLE, gate_relevance, gate_sufficiency, gate_verifiability, normalise_quote,
)
from .retrieve import Retriever

RETRY_HINT = (
    "\n\nYour previous answer was rejected because a supporting_quote did not "
    "appear verbatim in its clause. Copy quotes character-for-character."
)


@dataclass
class Result:
    answer: str
    refused: bool
    refusal_reason: str | None = None
    gate: str | None = None
    citations: list[dict] = field(default_factory=list)
    model_id: str | None = None
    latency_ms: int = 0


REFUSAL_TEXT = {
    "no_relevant_clause": "No clause in the corpus covers this. The corpus is the 5G NR "
                          "radio stack (TS 38.300/321/322/323/331) plus fault supervision "
                          "and performance measurements (TS 28.545/28.552).",
    "insufficient": "The retrieved clauses are on topic but do not contain the specific "
                    "information asked for.",
    "not_answerable_from_standards": "This asks about a live network. I am grounded only in "
                                     "3GPP specifications and have no access to telemetry.",
    "unverifiable": "An answer was produced but could not be verified against the cited "
                    "clause text, so it has been withheld.",
}


class Pipeline:
    def __init__(self, index_dir: Path, settings: Settings) -> None:
        self.settings = settings
        self.retriever = Retriever(Path(index_dir), settings.embedding_model)

    def _refuse(self, reason: str, gate: str, started: float) -> Result:
        return Result(answer=REFUSAL_TEXT[reason], refused=True, refusal_reason=reason,
                      gate=gate, latency_ms=int((time.monotonic() - started) * 1000))

    def answer(self, question: str, provider: str = "gemini",
               allow_failover: bool = True) -> Result:
        started = time.monotonic()
        # Pass the shaping settings explicitly; Retriever.search does not read them.
        hits = self.retriever.search(
            question,
            top_k=self.settings.top_k,
            per_spec_cap=self.settings.per_spec_cap,
            sibling_expand_from=self.settings.sibling_expand_from,
            sibling_cap=self.settings.sibling_cap,
        )

        reason = gate_relevance(hits, self.settings)
        if reason:
            return self._refuse(reason, "relevance", started)

        # One retry, only for a verifiability failure — re-prompting to copy the
        # quote exactly. Insufficient/live-network verdicts won't change on retry.
        answer = model_id = None
        for attempt in range(2):
            suffix = RETRY_HINT if attempt else ""
            answer, model_id = generate(
                question + suffix, hits, self.settings,
                provider=provider, allow_failover=allow_failover,
            )
            reason = gate_sufficiency(answer)
            if reason:
                return self._refuse(reason, "sufficiency", started)
            reason = gate_verifiability(answer, hits)
            if reason is None:
                break
        if reason:
            return self._refuse(UNVERIFIABLE, "verifiability", started)

        citations = [
            self._render_citation(citation.clause_id, citation.supporting_quote, hits)
            for citation in answer.citations
        ]
        return Result(answer=answer.answer, refused=False, citations=citations,
                      model_id=model_id,
                      latency_ms=int((time.monotonic() - started) * 1000))

    def _render_citation(self, clause_id: str, quote: str, hits) -> dict:
        """Resolve to the Chunk the quote came from (a split clause has several
        sharing one clause id). Gate 3 passed, so a match exists; fall back defensively."""
        parts = [h for h in hits if h.clause_id == clause_id]
        needle = normalise_quote(quote)
        source = next((h for h in parts if needle in normalise_quote(h.text)), parts[0])
        return {
            "clause_id": clause_id,
            "citation": source.citation(),
            "supporting_quote": quote,
            "text": source.text,
        }
