from pathlib import Path

from noc_copilot.evalset import load_questions

REPO = Path(__file__).resolve().parents[1]
QUESTIONS = REPO / "eval" / "questions.yaml"


def test_set_has_expected_shape():
    qs = load_questions(QUESTIONS)
    answerable = [q for q in qs if q.expect == "answer"]
    refusable = [q for q in qs if q.expect == "refuse"]
    assert len(answerable) >= 25
    assert len(refusable) >= 10


def test_answerable_questions_carry_gold_clauses():
    for q in load_questions(QUESTIONS):
        if q.expect == "answer":
            assert q.gold, f"{q.id} has no gold clause"


def test_refusable_questions_carry_a_reason_and_no_gold():
    for q in load_questions(QUESTIONS):
        if q.expect == "refuse":
            assert q.reason, f"{q.id} has no refusal reason"
            assert not q.gold


def test_gold_ids_are_spec_qualified():
    for q in load_questions(QUESTIONS):
        for gold in q.gold:
            assert "#" in gold, f"{q.id} gold {gold!r} must be 'spec_id#clause_id'"


def test_ids_are_unique():
    ids = [q.id for q in load_questions(QUESTIONS)]
    assert len(ids) == len(set(ids))


def test_coverage_includes_every_required_kind():
    kinds = {q.kind for q in load_questions(QUESTIONS) if q.expect == "answer"}
    assert {"single", "cross", "noc", "paraphrase"} <= kinds


def test_refusals_include_a_plausible_live_network_diagnostic():
    reasons = {q.reason for q in load_questions(QUESTIONS) if q.expect == "refuse"}
    assert "not_answerable_from_standards" in reasons


def test_refusal_reasons_are_the_ones_the_domain_model_defines():
    """CONTEXT.md names four Refusal Reasons. 'unverifiable' is a runtime outcome
    — a quote that could not be found — so it cannot be expected of a question."""
    allowed = {"no_relevant_clause", "insufficient", "not_answerable_from_standards"}
    for q in load_questions(QUESTIONS):
        if q.expect == "refuse":
            assert q.reason in allowed, f"{q.id} has unknown reason {q.reason!r}"


def test_cross_spec_questions_really_span_two_specifications():
    cross = [q for q in load_questions(QUESTIONS) if q.kind == "cross"]
    assert cross
    for q in cross:
        specs = {g.split("#")[0] for g in q.gold}
        assert len(specs) >= 2, f"{q.id} is labelled cross but cites only {specs}"
