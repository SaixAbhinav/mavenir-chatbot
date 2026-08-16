from pathlib import Path

import pytest

from noc_copilot.chunking import Chunk
from noc_copilot.retrieve import Retriever, rrf_fuse
from noc_copilot.store import build_index, embed_texts

MODEL = "BAAI/bge-small-en-v1.5"
REPO = Path(__file__).resolve().parents[1]


def chunk(cid, text):
    return Chunk(chunk_id=cid, spec_id="38.331", version="17.5.0", release="17",
                 clause_id=cid.split("#")[1], clause_title="T",
                 breadcrumb=f"TS 38.331 v17.5.0 § {cid.split('#')[1]} T", text=text)


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    index = tmp_path_factory.mktemp("index")
    build_index([
        chunk("38.331#5.3.5.3", "The UE shall start timer T310 upon detecting physical layer problems."),
        chunk("38.331#5.3.5.4", "Secondary cell group failure triggers an SCG failure information procedure."),
        chunk("38.322#5.3.2", "When the maximum number of retransmissions is reached, RLC indicates this to upper layers."),
    ], index, MODEL)
    return Retriever(index, MODEL)


def test_rrf_rewards_agreement_between_rankings():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "c"]], k=60)
    assert fused["b"] > fused["c"] and fused["a"] > fused["c"]


def test_rrf_top_score_is_rank_based_not_relevance_based():
    """Guards the design decision: RRF cannot be used for gating."""
    good = rrf_fuse([["relevant"]], k=60)
    bad = rrf_fuse([["totally_irrelevant"]], k=60)
    assert good["relevant"] == bad["totally_irrelevant"]


def test_exact_identifier_query_finds_the_right_clause(retriever):
    hits = retriever.search("T310", top_k=3)
    assert hits[0].clause_id == "5.3.5.3"


def test_paraphrased_query_still_retrieves(retriever):
    hits = retriever.search("what happens after too many failed resends?", top_k=3)
    assert "5.3.2" in {h.clause_id for h in hits}


def test_hits_carry_raw_scores_distinct_from_rrf(retriever):
    hits = retriever.search("T310", top_k=3)
    assert 0.0 <= hits[0].cosine <= 1.0
    assert hits[0].bm25 >= 0.0
    assert hits[0].rrf != hits[0].cosine


def test_off_topic_query_has_low_raw_cosine(retriever):
    """The signal Gate 1 actually depends on."""
    on = retriever.search("T310 timer", top_k=1)[0].cosine
    off = retriever.search("peak throughput of Wi-Fi 7", top_k=1)[0].cosine
    assert off < on


def test_hit_found_only_by_bm25_still_carries_its_true_cosine(retriever, monkeypatch):
    """Gate 1 thresholds the raw cosine. If a Hit that reached the top on BM25
    alone carried a placeholder cosine of 0.0, it would be refused on a score it
    never earned — a false refusal with no visible cause."""
    monkeypatch.setattr("noc_copilot.retrieve.CANDIDATES", 1)
    query = "how many resends before giving up"

    embedding = embed_texts([query], MODEL)[0]
    cosines = [sum(a * b for a, b in zip(embedding, v)) for v in retriever.embeddings]
    dense_only = [retriever.ids[max(range(len(cosines)), key=lambda i: cosines[i])]]

    hits = retriever.search(query, top_k=2)
    outside_dense = [h for h in hits if h.chunk_id not in dense_only]
    assert outside_dense, "query no longer exercises the BM25-only path"

    for hit in outside_dense:
        vector = retriever.embeddings[retriever._position[hit.chunk_id]]
        expected = sum(a * b for a, b in zip(embedding, vector))
        assert hit.cosine == pytest.approx(expected)
        assert hit.cosine != 0.0


@pytest.mark.skipif(not (REPO / "data" / "index" / "chroma.sqlite3").exists(),
                    reason="committed index not present")
def test_dense_search_is_exact_against_the_real_corpus():
    """Regression for approximate-search recall loss.

    Chroma's HNSW defaults to search_ef=10, so asking for 50 neighbours over the
    real 2,085-chunk index returned only 18 of the true top-50 for this question
    and dropped the exact nearest neighbour entirely — TS 28.545 §8, which is
    both the best dense and the best BM25 match, never reached fusion.
    """
    from noc_copilot.config import load_settings

    settings = load_settings(REPO / "config" / "settings.yaml")
    retriever = Retriever(REPO / "data" / "index", settings.embedding_model)
    question = ("How are VNF application alarms correlated with alarms related to "
                "virtualised resources?")

    hits = retriever.search(question, top_k=8)
    assert hits[0].chunk_id == "28.545#8", [h.chunk_id for h in hits]


def test_per_spec_cap_stops_one_specification_filling_the_context(retriever):
    hits = retriever.search("failure", top_k=3, per_spec_cap=1)
    # The cap shapes the ranked results. Sibling expansion deliberately adds
    # same-parent neighbours afterwards, which are necessarily the same spec.
    ranked_38331 = [h for h in hits if h.spec_id == "38.331" and not h.expanded]
    assert len(ranked_38331) == 1


def test_sibling_expansion_adds_neighbours_and_marks_them(retriever):
    """A procedure split across sibling clauses is completed after ranking, so
    the additions are visibly not ranked results: rrf is 0.0 and expanded is
    True. Gate 1 must threshold only the ranked Hits."""
    hits = retriever.search("T310", top_k=1, sibling_expand_from=1, sibling_cap=4)
    ranked = [h for h in hits if not h.expanded]
    expanded = [h for h in hits if h.expanded]

    assert len(ranked) == 1 and ranked[0].clause_id == "5.3.5.3"
    assert [h.clause_id for h in expanded] == ["5.3.5.4"]
    assert all(h.rrf == 0.0 for h in expanded)
    assert hits.index(ranked[0]) < hits.index(expanded[0])
    # An expanded Hit still carries real scores, so it can be cited and gated.
    assert 0.0 < expanded[0].cosine <= 1.0


def test_sibling_expansion_never_duplicates_a_ranked_hit(retriever):
    hits = retriever.search("T310", top_k=3, sibling_expand_from=3, sibling_cap=8)
    ids = [h.chunk_id for h in hits]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not (REPO / "data" / "index" / "chroma.sqlite3").exists(),
                    reason="committed index not present")
def test_sibling_expansion_recovers_a_known_miss_on_the_real_corpus():
    """q001 of the frozen set. TS 38.331 §5.3.7.2 Initiation is the gold clause;
    ranking returns its sibling §5.3.7.1 General instead."""
    from noc_copilot.config import load_settings

    settings = load_settings(REPO / "config" / "settings.yaml")
    retriever = Retriever(REPO / "data" / "index", settings.embedding_model)
    question = "What conditions cause the UE to initiate the RRC connection re-establishment procedure?"

    def clauses(hits):
        # Recall is measured on clause ids: an oversized clause splits into
        # several chunks (§5.3.7.2 becomes .../0 and .../1).
        return {f"{h.spec_id}#{h.clause_id}" for h in hits}

    plain = retriever.search(question, top_k=settings.top_k, sibling_cap=0)
    assert "38.331#5.3.7.2" not in clauses(plain)

    shaped = retriever.search(question, top_k=settings.top_k,
                              per_spec_cap=settings.per_spec_cap,
                              sibling_expand_from=settings.sibling_expand_from,
                              sibling_cap=settings.sibling_cap)
    assert "38.331#5.3.7.2" in clauses(shaped)


def test_results_are_ordered_by_rrf(retriever):
    hits = retriever.search("RLC retransmissions", top_k=3)
    assert [h.rrf for h in hits] == sorted([h.rrf for h in hits], reverse=True)
