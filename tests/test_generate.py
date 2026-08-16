import pytest

from noc_copilot.generate import build_prompt
from noc_copilot.retrieve import Hit
from noc_copilot.schemas import Answer, Citation


def hit(clause_id="5.3.5.3", text="The UE shall start timer T310."):
    return Hit(chunk_id=f"38.331#{clause_id}", clause_id=clause_id, spec_id="38.331",
               version="17.5.0", breadcrumb="B", text=text,
               cosine=0.8, bm25=5.0, rrf=0.016)


def test_prompt_contains_every_retrieved_clause():
    prompt = build_prompt("When does T310 start?", [hit("5.3.5.3"), hit("5.3.5.4", "SCG failure.")])
    assert "5.3.5.3" in prompt and "5.3.5.4" in prompt
    assert "The UE shall start timer T310." in prompt


def test_prompt_states_the_scope_boundary():
    prompt = build_prompt("Why is cell 4412 dropping calls?", [hit()])
    assert "no access to live network telemetry" in prompt.lower()


def test_prompt_demands_verbatim_quotes():
    assert "verbatim" in build_prompt("q", [hit()]).lower()


def test_answer_schema_round_trips():
    answer = Answer.model_validate({
        "answer": "T310 starts on physical layer problems.",
        "sufficient": True,
        "answerable_from_standards": True,
        "citations": [{"clause_id": "5.3.5.3", "supporting_quote": "The UE shall start timer T310."}],
    })
    assert answer.citations[0].clause_id == "5.3.5.3"


def test_answer_schema_rejects_missing_quote():
    with pytest.raises(Exception):
        Citation.model_validate({"clause_id": "5.3.5.3"})


def test_insufficient_answer_needs_no_citations():
    answer = Answer.model_validate({
        "answer": "The provided clauses do not specify this.",
        "sufficient": False, "answerable_from_standards": True, "citations": [],
    })
    assert answer.sufficient is False


def settings(**over):
    from noc_copilot.config import Settings
    base = dict(embedding_model="m", gemini_model="g", groq_model="q", top_k=8,
                max_chunk_chars=6000, session_cap=20, daily_cap=500)
    return Settings(**{**base, **over})


def test_transient_provider_error_is_retried_on_the_same_model(monkeypatch):
    """A 503 from Gemini is common and temporary. Failover cannot cover it —
    the Groq free tier rejects a prompt this size — so the same model is
    retried before giving up. Retrying one model keeps the eval single-model."""
    from noc_copilot import generate as gen

    calls = []

    def flaky(prompt, model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("503 UNAVAILABLE. This model is experiencing high demand")
        return Answer(answer="ok", sufficient=True, answerable_from_standards=True, citations=[])

    monkeypatch.setattr(gen, "_gemini", flaky)
    monkeypatch.setattr(gen, "_sleep", lambda seconds: None)
    answer, model = gen.generate("q", [hit()], settings(), allow_failover=False)
    assert answer.answer == "ok"
    assert calls == ["g", "g"]


def test_a_permanent_error_is_not_retried_forever(monkeypatch):
    from noc_copilot import generate as gen

    calls = []

    def broken(prompt, model):
        calls.append(model)
        raise RuntimeError("400 invalid schema")

    monkeypatch.setattr(gen, "_gemini", broken)
    monkeypatch.setattr(gen, "_sleep", lambda seconds: None)
    with pytest.raises(gen.GenerationError):
        gen.generate("q", [hit()], settings(), allow_failover=False)
    assert calls == ["g"], "a non-transient error must not be retried"


def test_failover_is_suppressed_when_the_caller_forbids_it(monkeypatch):
    """evaluate.py pins one provider so a rate limit fails loudly instead of
    silently publishing a table blended from two models."""
    from noc_copilot import generate as gen

    used = []
    monkeypatch.setattr(gen, "_sleep", lambda seconds: None)
    monkeypatch.setattr(gen, "_gemini", lambda p, m: (_ for _ in ()).throw(RuntimeError("429 rate limit")))
    monkeypatch.setattr(gen, "_groq", lambda p, m: used.append(m) or Answer(
        answer="groq", sufficient=True, answerable_from_standards=True, citations=[]))

    with pytest.raises(gen.GenerationError):
        gen.generate("q", [hit()], settings(), allow_failover=False)
    assert used == []

    answer, _ = gen.generate("q", [hit()], settings(), allow_failover=True)
    assert answer.answer == "groq"


def test_expanded_hits_are_presented_as_clauses_like_any_other():
    """A sibling added after ranking is still citable, so it must appear in the
    prompt. Nothing about ranking belongs in the model's view."""
    ranked = hit("5.3.7.1", "General.")
    expanded = hit("5.3.7.2", "The UE initiates the procedure when...")
    expanded.expanded = True
    prompt = build_prompt("q", [ranked, expanded])
    assert "5.3.7.2" in prompt and "The UE initiates the procedure when..." in prompt
    assert "expanded" not in prompt.lower()
