"""Fit Gate 1 thresholds on the frozen eval set.

Chooses the pair maximising (out-of-scope correctly gated) - (in-scope wrongly
gated), so the threshold is fitted rather than guessed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from noc_copilot.config import load_settings  # noqa: E402
from noc_copilot.evalset import load_questions  # noqa: E402
from noc_copilot.retrieve import Retriever  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = load_settings(REPO / "config" / "settings.yaml")
    retriever = Retriever(REPO / "data" / "index", settings.embedding_model)
    questions = load_questions(REPO / "eval" / "questions.yaml")

    observed = []
    for question in questions:
        hits = retriever.search(
            question.question,
            top_k=settings.top_k,
            per_spec_cap=settings.per_spec_cap,
            sibling_expand_from=settings.sibling_expand_from,
            sibling_cap=settings.sibling_cap,
        )

        ranked = [h for h in hits if not h.expanded]
        observed.append((
            question.expect,
            max((h.cosine for h in ranked), default=0.0),
            max((h.bm25 for h in ranked), default=0.0),
        ))

    for expect in ("answer", "refuse"):
        rows = [(c, b) for e, c, b in observed if e == expect]
        print(f"{expect}: cosine {min(c for c, _ in rows):.3f}-{max(c for c, _ in rows):.3f}, "
              f"bm25 {min(b for _, b in rows):.2f}-{max(b for _, b in rows):.2f}")

    best, best_score = (0.0, 0.0), -999
    for cosine_t in [i / 100 for i in range(30, 90)]:
        for bm25_t in [i / 2 for i in range(0, 40)]:
            gated = [(e, c < cosine_t and b < bm25_t) for e, c, b in observed]
            caught = sum(1 for e, g in gated if e == "refuse" and g)
            wrong = sum(1 for e, g in gated if e == "answer" and g)
            score = caught - 2 * wrong  # false refusals cost double
            if score > best_score:
                best, best_score = (cosine_t, bm25_t), score

    print(f"\ncosine_threshold: {best[0]}\nbm25_threshold: {best[1]}")
    print("Write these into config/settings.yaml.")


if __name__ == "__main__":
    main()
