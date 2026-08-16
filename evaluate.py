"""Evaluation harness. Pins one provider per run; resumable via --resume, with
each answered question checkpointed so a rate-limit or crash loses nothing."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from noc_copilot.config import load_settings  # noqa: E402
from noc_copilot.evalset import load_questions  # noqa: E402
from noc_copilot.pipeline import Pipeline  # noqa: E402

load_dotenv(Path(__file__).resolve().parent / ".env")
REPO = Path(__file__).resolve().parent
CALL_DELAY_SECONDS = 2.0  # keep a pinned run under the free-tier rate limit

JUDGE_PROMPT = """\
You are checking whether an answer is supported by the clauses it cites.

QUESTION: {question}
ANSWER: {answer}
CITED CLAUSE TEXT:
{clauses}

Does every factual claim in the answer follow from the cited clause text?
Reply with exactly one word: GROUNDED or UNGROUNDED."""


def score_retrieval(hits, gold: list[str]) -> bool:
    retrieved = {f"{h.spec_id}#{h.clause_id}" for h in hits}
    return all(g in retrieved for g in gold)


# Groq free tier caps a request at 8,000 TPM; keep the judge prompt under it.
JUDGE_PROMPT_TOKEN_BUDGET = 7000


def _estimate_tokens(text: str) -> int:
    # Deliberately high (3GPP text is token-dense) so the estimate never
    # undershoots the tokenizer. ceil(len / 3).
    return -(-len(text) // 3)


def _fit_clauses(question: str, answer: str, citations: list[dict]) -> str:
    """Clause evidence for the judge, fitted under Groq's 8,000 TPM cap.

    Full clause text where it fits, else each citation's supporting_quote, then
    truncated quotes — never dropping a citation.
    """
    overhead = _estimate_tokens(
        JUDGE_PROMPT.format(question=question, answer=answer, clauses=""))
    budget_chars = max(500, JUDGE_PROMPT_TOKEN_BUDGET - overhead) * 3

    def block(get_text) -> str:
        return "\n\n".join(f"[{c['citation']}]\n{get_text(c)}" for c in citations)

    full = block(lambda c: c["text"])
    if len(full) <= budget_chars:
        return full
    quotes = block(lambda c: c["supporting_quote"])
    if len(quotes) <= budget_chars:
        return quotes
    share = max(120, budget_chars // max(1, len(citations)) - 40)
    return block(lambda c: c["supporting_quote"][:share])


def judge_groundedness(question, answer, citations, settings) -> bool:
    """Judge groundedness on Groq — a different model than the generator, to
    avoid the self-preference bias of a model grading its own output."""
    from groq import Groq

    clauses = _fit_clauses(question, answer, citations)
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            question=question, answer=answer, clauses=clauses)}],
        temperature=0,
        max_tokens=400,  # gpt-oss-120b spends tokens on reasoning before the verdict
    )
    return "UNGROUNDED" not in (response.choices[0].message.content or "").upper()


def summarise(records: list[dict]) -> dict:
    answerable = [r for r in records if r["expect"] == "answer"]
    refusable = [r for r in records if r["expect"] == "refuse"]
    answered = [r for r in answerable if not r["refused"]]
    judged = [r for r in answered if r["grounded"] is not None]

    def ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 3) if denominator else 0.0

    return {
        "n_answerable": len(answerable),
        "n_refusable": len(refusable),
        "recall_at_k": ratio(sum(1 for r in answerable if r["retrieved_gold"]), len(answerable)),
        "false_refusal_rate": ratio(sum(1 for r in answerable if r["refused"]), len(answerable)),
        "refusal_rate_out_of_scope": ratio(sum(1 for r in refusable if r["refused"]), len(refusable)),
        "groundedness": ratio(sum(1 for r in judged if r["grounded"]), len(judged)),
    }


def pending_questions(questions, existing_records: list[dict]) -> list:
    """Questions not already answered in a prior (resumed) run, in order."""
    done = {r["id"] for r in existing_records}
    return [q for q in questions if q.id not in done]


def is_quota_error(exc: Exception) -> bool:
    """True when a provider declined for rate/quota reasons rather than a bug."""
    text = repr(exc).upper()
    return any(
        marker in text
        for marker in ("RESOURCE_EXHAUSTED", "429", "RATE_LIMIT", "QUOTA", "413")
    )


# Gemini's short rolling rate window returns a 429 with a "retry in Ns" hint and
# clears within a minute; wait it out rather than ending the run on the first one.
MAX_RATE_WAIT_SECONDS = 120
MAX_RATE_RETRIES = 8
# A 503 overload spike carries no retry hint; back off a fixed interval instead.
TRANSIENT_BACKOFF_SECONDS = 15


def retry_after_seconds(exc: Exception) -> float | None:
    """The delay a provider asked us to wait, if it gave a short one."""
    import re

    text = repr(exc)
    match = (re.search(r"retry in ([0-9.]+)\s*s", text, re.IGNORECASE)
             or re.search(r"retryDelay['\"\s:]+([0-9.]+)s", text))
    return float(match.group(1)) if match else None


def is_transient_error(exc: Exception) -> bool:
    """A provider overload (503) worth waiting out rather than crashing on."""
    text = repr(exc).upper()
    return any(m in text for m in ("503", "UNAVAILABLE", "OVERLOADED", "HIGH DEMAND"))


def _load_existing(out_path: Path) -> list[dict]:
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8")).get("records", [])
    return []


def _write_results(out_path: Path, provider: str, model_id: str,
                   records: list[dict], complete: bool,
                   judge_model: str | None = None) -> None:
    summary = summarise(records)
    gates: dict[str, int] = {}
    for record in records:
        if record["refused"]:
            gates[record["gate"]] = gates.get(record["gate"], 0) + 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"provider": provider, "model_id": model_id, "judge_model": judge_model,
         "complete": complete, "n_answered": len(records), "summary": summary,
         "refusals_by_gate": gates, "records": records}, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    parser.add_argument("--judge", action="store_true", help="run the groundedness judge")
    parser.add_argument("--resume", action="store_true",
                        help="continue a prior run, skipping already-answered questions")
    args = parser.parse_args()

    settings = load_settings(REPO / "config" / "settings.yaml")
    pipeline = Pipeline(REPO / "data" / "index", settings)
    questions = load_questions(REPO / "eval" / "questions.yaml")
    model_id = settings.gemini_model if args.provider == "gemini" else settings.groq_model
    judge_model = settings.groq_model if args.judge else None
    out = REPO / "eval" / "results" / f"{args.provider}.json"

    records = _load_existing(out) if args.resume else []
    todo = pending_questions(questions, records)
    if args.resume and records:
        print(f"Resuming: {len(records)} already answered, {len(todo)} remaining.")

    for question in todo:
        waits = 0
        while True:
            try:
                # Pass the shaping settings explicitly, matching Pipeline.answer.
                hits = pipeline.retriever.search(
                    question.question,
                    top_k=settings.top_k,
                    per_spec_cap=settings.per_spec_cap,
                    sibling_expand_from=settings.sibling_expand_from,
                    sibling_cap=settings.sibling_cap,
                )
                # allow_failover=False: fail loudly rather than blending two models.
                result = pipeline.answer(question.question, provider=args.provider,
                                         allow_failover=False)
                grounded = None
                if args.judge and not result.refused and question.expect == "answer":
                    grounded = judge_groundedness(question.question, result.answer,
                                                  result.citations, settings)
                break
            except Exception as exc:
                if is_quota_error(exc):
                    wait = retry_after_seconds(exc)
                    if wait is not None and wait <= MAX_RATE_WAIT_SECONDS and waits < MAX_RATE_RETRIES:
                        # Short rolling-window limit: wait it out, retry the question.
                        waits += 1
                        _write_results(out, args.provider, model_id, records,
                                       complete=False, judge_model=judge_model)
                        print(f"{question.id}: rate-limited, waiting {wait:.0f}s "
                              f"(retry {waits}/{MAX_RATE_RETRIES})")
                        time.sleep(wait + 2.0)
                        continue
                    # No short hint (or retries exhausted): daily cap. Save and stop.
                    _write_results(out, args.provider, model_id, records, complete=False,
                                   judge_model=judge_model)
                    print(f"\nProvider quota reached at {question.id}. "
                          f"{len(records)} answered, {len(todo) - len(records)}... remaining.")
                    print(f"Saved progress to {out}. Re-run with --resume once the quota resets.")
                    raise SystemExit(0)
                if is_transient_error(exc) and waits < MAX_RATE_RETRIES:
                    # 503/overload spike: back off and retry the same question.
                    waits += 1
                    _write_results(out, args.provider, model_id, records,
                                   complete=False, judge_model=judge_model)
                    print(f"{question.id}: provider unavailable, waiting "
                          f"{TRANSIENT_BACKOFF_SECONDS}s (retry {waits}/{MAX_RATE_RETRIES})")
                    time.sleep(TRANSIENT_BACKOFF_SECONDS)
                    continue
                raise

        records.append({
            "id": question.id, "expect": question.expect, "kind": question.kind,
            "question": question.question, "gold": question.gold,
            "retrieved_gold": score_retrieval(hits, question.gold) if question.gold else None,
            "refused": result.refused, "refusal_reason": result.refusal_reason,
            "gate": result.gate, "grounded": grounded,
            "answer": result.answer, "latency_ms": result.latency_ms,
        })
        # Checkpoint after every question so a crash or quota-exit loses nothing.
        _write_results(out, args.provider, model_id, records, complete=False,
                       judge_model=judge_model)
        flag = "REFUSED" if result.refused else "answered"
        print(f"{question.id}: {flag} ({result.refusal_reason or result.gate or '-'})")
        time.sleep(CALL_DELAY_SECONDS)

    _write_results(out, args.provider, model_id, records, complete=True,
                   judge_model=judge_model)
    summary = summarise(records)
    gates: dict[str, int] = {}
    for record in records:
        if record["refused"]:
            gates[record["gate"]] = gates.get(record["gate"], 0) + 1

    print(f"\n--- {args.provider} / {model_id} ({len(records)} questions) ---")
    for key, value in summary.items():
        print(f"{key:34s} {value}")
    print(f"refusals by gate: {gates}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
