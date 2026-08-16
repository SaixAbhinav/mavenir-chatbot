from unittest.mock import patch

import pytest

from noc_copilot.config import Settings
from noc_copilot.pipeline import Pipeline
from noc_copilot.retrieve import Hit
from noc_copilot.schemas import Answer, Citation

SETTINGS = Settings(embedding_model="BAAI/bge-small-en-v1.5", gemini_model="g",
                    groq_model="q", top_k=8, max_chunk_chars=6000,
                    cosine_threshold=0.55, bm25_threshold=4.0,
                    session_cap=20, daily_cap=500)


def hit(cosine=0.8, bm25=6.0, text="The UE shall start timer T310.",
        clause_id="5.3.5.3", chunk_id=None, expanded=False):
    return Hit(chunk_id=chunk_id or f"38.331#{clause_id}", clause_id=clause_id,
               spec_id="38.331", version="17.5.0", breadcrumb="B", text=text,
               cosine=cosine, bm25=bm25, rrf=0.0 if expanded else 0.016, expanded=expanded)


@pytest.fixture
def pipeline(tmp_path):
    with patch("noc_copilot.pipeline.Retriever"):
        return Pipeline(tmp_path, SETTINGS)


def test_weak_retrieval_refuses_before_calling_the_model(pipeline):
    pipeline.retriever.search.return_value = [hit(cosine=0.1, bm25=0.2)]
    with patch("noc_copilot.pipeline.generate") as gen:
        result = pipeline.answer("What is Wi-Fi 7 throughput?")
    gen.assert_not_called()
    assert result.refused and result.refusal_reason == "no_relevant_clause"
    assert result.gate == "relevance"


def test_good_answer_passes_all_gates(pipeline):
    pipeline.retriever.search.return_value = [hit()]
    good = Answer(answer="T310 starts on physical layer problems.", sufficient=True,
                  answerable_from_standards=True,
                  citations=[Citation(clause_id="5.3.5.3",
                                      supporting_quote="The UE shall start timer T310.")])
    with patch("noc_copilot.pipeline.generate", return_value=(good, "g")):
        result = pipeline.answer("When does T310 start?")
    assert not result.refused
    assert result.citations[0]["citation"] == "TS 38.331 v17.5.0 §5.3.5.3"
    assert result.model_id == "g"


def test_paraphrased_quote_is_refused_after_one_retry(pipeline):
    pipeline.retriever.search.return_value = [hit()]
    bad = Answer(answer="A.", sufficient=True, answerable_from_standards=True,
                 citations=[Citation(clause_id="5.3.5.3", supporting_quote="T310 starts quickly.")])
    with patch("noc_copilot.pipeline.generate", return_value=(bad, "g")) as gen:
        result = pipeline.answer("When does T310 start?")
    assert gen.call_count == 2          # one retry, then refuse
    assert result.refusal_reason == "unverifiable"


def test_generation_failure_surfaces_as_an_error_not_an_answer(pipeline):
    from noc_copilot.generate import GenerationError
    pipeline.retriever.search.return_value = [hit()]
    with patch("noc_copilot.pipeline.generate", side_effect=GenerationError("both down")):
        with pytest.raises(GenerationError):
            pipeline.answer("When does T310 start?")


def test_latency_is_recorded(pipeline):
    pipeline.retriever.search.return_value = [hit(cosine=0.1, bm25=0.2)]
    assert pipeline.answer("q").latency_ms >= 0


def test_retrieval_is_called_with_the_configured_shaping(pipeline):
    """The pipeline must pass per_spec_cap and sibling settings through, or the
    retriever's plain defaults undo the recall work of Task 9 (findings §4.21).
    Retriever.search does not read settings.yaml itself."""
    pipeline.retriever.search.return_value = [hit(cosine=0.1, bm25=0.2)]
    pipeline.answer("q")
    _, kwargs = pipeline.retriever.search.call_args
    assert kwargs["top_k"] == SETTINGS.top_k
    assert kwargs["per_spec_cap"] == SETTINGS.per_spec_cap
    assert kwargs["sibling_expand_from"] == SETTINGS.sibling_expand_from
    assert kwargs["sibling_cap"] == SETTINGS.sibling_cap


def test_citation_display_resolves_to_the_chunk_holding_the_quote(pipeline):
    """A split clause has several chunks sharing one clause id. The displayed
    clause text must be the part the quote actually came from, not an arbitrary
    one — the hosted demo shows this text as the evidence."""
    part0 = hit(clause_id="5.3.7.2", chunk_id="38.331#5.3.7.2/0",
                text="The UE initiates the procedure when one of the following.")
    part1 = hit(clause_id="5.3.7.2", chunk_id="38.331#5.3.7.2/1",
                text="upon integrity check failure indication from lower layers;")
    pipeline.retriever.search.return_value = [part0, part1]
    good = Answer(answer="A.", sufficient=True, answerable_from_standards=True,
                  citations=[Citation(clause_id="5.3.7.2",
                                      supporting_quote="upon integrity check failure indication from lower layers;")])
    with patch("noc_copilot.pipeline.generate", return_value=(good, "g")):
        result = pipeline.answer("q")
    assert result.citations[0]["text"] == part1.text
