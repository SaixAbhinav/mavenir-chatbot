from evaluate import (
    is_quota_error, pending_questions, score_retrieval, summarise,
)
from noc_copilot.evalset import EvalQuestion
from noc_copilot.retrieve import Hit


def hit(spec_id, clause_id):
    return Hit(chunk_id=f"{spec_id}#{clause_id}", clause_id=clause_id, spec_id=spec_id,
               version="17.5.0", breadcrumb="B", text="t", cosine=0.8, bm25=5.0, rrf=0.016)


def test_retrieval_hit_requires_every_gold_clause():
    hits = [hit("38.331", "5.3.5.3"), hit("38.322", "5.3.2")]
    assert score_retrieval(hits, ["38.331#5.3.5.3"]) is True
    assert score_retrieval(hits, ["38.331#5.3.5.3", "38.322#5.3.2"]) is True
    assert score_retrieval(hits, ["38.331#5.3.5.3", "38.321#5.1.1"]) is False


def test_retrieval_match_is_spec_qualified():
    """A clause id alone is ambiguous across specifications."""
    assert score_retrieval([hit("38.322", "5.3.2")], ["38.331#5.3.2"]) is False


def test_summarise_computes_the_published_metrics():
    records = [
        {"expect": "answer", "refused": False, "retrieved_gold": True, "grounded": True},
        {"expect": "answer", "refused": True, "retrieved_gold": True, "grounded": None},
        {"expect": "refuse", "refused": True, "retrieved_gold": None, "grounded": None},
        {"expect": "refuse", "refused": False, "retrieved_gold": None, "grounded": False},
    ]
    summary = summarise(records)
    assert summary["recall_at_k"] == 1.0
    assert summary["false_refusal_rate"] == 0.5
    assert summary["refusal_rate_out_of_scope"] == 0.5
    assert summary["groundedness"] == 1.0


def test_summarise_handles_an_empty_run():
    assert summarise([])["recall_at_k"] == 0.0


def q(qid, expect="answer"):
    return EvalQuestion(id=qid, question=f"q{qid}", expect=expect)


def test_pending_skips_already_answered_questions():
    questions = [q("a1"), q("a2"), q("a3")]
    existing = [{"id": "a1"}, {"id": "a3"}]
    assert [x.id for x in pending_questions(questions, existing)] == ["a2"]


def test_pending_returns_all_when_nothing_done():
    questions = [q("a1"), q("a2")]
    assert [x.id for x in pending_questions(questions, [])] == ["a1", "a2"]


def test_pending_preserves_order():
    questions = [q("a1"), q("a2"), q("a3"), q("a4")]
    existing = [{"id": "a2"}]
    assert [x.id for x in pending_questions(questions, existing)] == ["a1", "a3", "a4"]


def test_quota_error_detects_free_tier_429():
    assert is_quota_error(Exception("gemini: 429 RESOURCE_EXHAUSTED quota exceeded"))
    assert is_quota_error(RuntimeError("Request too large ... 413 rate_limit_exceeded"))


def test_quota_error_ignores_ordinary_bugs():
    assert not is_quota_error(KeyError("clause_id"))
    assert not is_quota_error(ValueError("bad schema"))
