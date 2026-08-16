from noc_copilot.config import Settings
from noc_copilot.guards import (
    NO_RELEVANT_CLAUSE, INSUFFICIENT, NOT_ANSWERABLE_FROM_STANDARDS, UNVERIFIABLE,
    gate_relevance, gate_sufficiency, gate_verifiability, normalise_quote,
)
from noc_copilot.retrieve import Hit
from noc_copilot.schemas import Answer, Citation

SETTINGS = Settings(embedding_model="m", top_k=8, max_chunk_chars=6000,
                    cosine_threshold=0.55, bm25_threshold=4.0,
                    session_cap=20, daily_cap=500)


def hit(clause_id="5.3.5.3", text="The UE shall start timer T310.", cosine=0.8, bm25=6.0,
        chunk_id=None, expanded=False):
    return Hit(chunk_id=chunk_id or f"38.331#{clause_id}", clause_id=clause_id,
               spec_id="38.331", version="17.5.0", breadcrumb="B", text=text,
               cosine=cosine, bm25=bm25, rrf=0.0 if expanded else 0.016, expanded=expanded)


def answer(quote="The UE shall start timer T310.", clause_id="5.3.5.3",
           sufficient=True, answerable=True):
    return Answer(answer="A.", sufficient=sufficient, answerable_from_standards=answerable,
                  citations=[Citation(clause_id=clause_id, supporting_quote=quote)])


# Gate 1
def test_gate1_passes_strong_retrieval():
    assert gate_relevance([hit()], SETTINGS) is None


def test_gate1_refuses_when_both_signals_are_weak():
    assert gate_relevance([hit(cosine=0.2, bm25=0.5)], SETTINGS) == NO_RELEVANT_CLAUSE


def test_gate1_passes_when_only_bm25_is_strong():
    """Exact identifier matches must survive weak dense similarity."""
    assert gate_relevance([hit(cosine=0.2, bm25=9.0)], SETTINGS) is None


def test_gate1_refuses_on_empty_retrieval():
    assert gate_relevance([], SETTINGS) == NO_RELEVANT_CLAUSE


def test_gate1_ignores_hits_added_by_sibling_expansion():
    """An expanded Hit was never ranked — it is in the context only because a
    neighbour scored well. Letting it answer the question 'did retrieval find
    anything?' would let a sibling rescue a retrieval that found nothing."""
    weak_ranked = hit(cosine=0.2, bm25=0.5)
    strong_sibling = hit("5.3.5.4", cosine=0.9, bm25=9.0, expanded=True)
    assert gate_relevance([weak_ranked, strong_sibling], SETTINGS) == NO_RELEVANT_CLAUSE


def test_gate1_is_inactive_until_calibrated():
    uncalibrated = SETTINGS.model_copy(update={"cosine_threshold": None,
                                               "bm25_threshold": None})
    assert gate_relevance([hit(cosine=0.01, bm25=0.0)], uncalibrated) is None


# Gate 2
def test_gate2_refuses_insufficient():
    assert gate_sufficiency(answer(sufficient=False)) == INSUFFICIENT


def test_gate2_refuses_live_network_questions():
    assert gate_sufficiency(answer(answerable=False)) == NOT_ANSWERABLE_FROM_STANDARDS


def test_gate2_passes_a_good_answer():
    assert gate_sufficiency(answer()) is None


# Gate 3
def test_gate3_passes_a_verbatim_quote():
    assert gate_verifiability(answer(), [hit()]) is None


def test_gate3_tolerates_whitespace_and_case_differences():
    assert gate_verifiability(answer(quote="the ue  shall START timer t310."), [hit()]) is None


def test_gate3_rejects_a_fabricated_clause_id():
    assert gate_verifiability(answer(clause_id="9.9.9"), [hit()]) == UNVERIFIABLE


def test_gate3_rejects_a_paraphrased_quote():
    assert gate_verifiability(answer(quote="The UE starts T310 promptly."), [hit()]) == UNVERIFIABLE


def test_gate3_rejects_a_quote_from_a_different_clause():
    hits = [hit("5.3.5.3", "The UE shall start timer T310."),
            hit("5.3.5.4", "Secondary cell group failure.")]
    bad = answer(quote="Secondary cell group failure.", clause_id="5.3.5.3")
    assert gate_verifiability(bad, hits) == UNVERIFIABLE


def test_gate3_rejects_an_answer_with_no_citations():
    empty = Answer(answer="A.", sufficient=True, answerable_from_standards=True, citations=[])
    assert gate_verifiability(empty, [hit()]) == UNVERIFIABLE


def test_gate3_searches_every_chunk_of_a_split_clause():
    """An oversized clause becomes several Chunks sharing one clause id —
    TS 38.331 §5.3.7.2 is two. A quote from the first part must verify even
    though a later part carries the same clause id."""
    hits = [hit("5.3.7.2", "The UE initiates the procedure when one of the following.",
                chunk_id="38.331#5.3.7.2/0"),
            hit("5.3.7.2", "upon integrity check failure indication from lower layers;",
                chunk_id="38.331#5.3.7.2/1")]
    assert gate_verifiability(answer(quote="The UE initiates the procedure when one of the following.",
                                     clause_id="5.3.7.2"), hits) is None
    assert gate_verifiability(answer(quote="upon integrity check failure indication from lower layers;",
                                     clause_id="5.3.7.2"), hits) is None


def test_gate3_rejects_the_real_spliced_quote_that_a_model_produced():
    """Regression from findings §4.23. gemini-2.5-flash welded the opening of
    one bullet of TS 38.331 §5.3.10.1 to the continuation of another, inventing
    a sentence that appears nowhere in the specification."""
    clause = ("The UE shall:\n\n1>\tif any DAPS bearer is configured, upon receiving N310 "
              "consecutive \"out-of-sync\" indications for the source SpCell from lower "
              "layers and T304 is running:\n\n2>\tstart timer T310 for the source SpCell.")
    spliced = ('upon receiving N310 consecutive "out-of-sync" indications for the SpCell '
               'from lower layers while neither T300, T301, T304, T311 nor T319 are running')
    bad = answer(quote=spliced, clause_id="5.3.10.1")
    assert gate_verifiability(bad, [hit("5.3.10.1", clause)]) == UNVERIFIABLE


def test_normalise_quote_collapses_whitespace_and_case():
    assert normalise_quote("  The  UE\nSHALL  ") == "the ue shall"
