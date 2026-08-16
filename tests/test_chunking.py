from noc_copilot.chunking import build_chunks
from noc_copilot.clauses import Clause
from noc_copilot.config import SpecEntry

SPEC = SpecEntry(spec_id="38.331", series="38", title="t", role="CU", version="17.5.0")


def clause(cid="5.3.5.3", title="Reception", body="The UE shall comply.", ancestors=None):
    return Clause(cid, title, body, ancestors or [("5.3", "Connection control"),
                                                  ("5.3.5", "RRC reconnection")])


def test_breadcrumb_contains_spec_version_and_full_ancestry():
    chunk = build_chunks([clause()], SPEC, "17", 6000)[0]
    assert chunk.breadcrumb == (
        "TS 38.331 v17.5.0 § 5.3 Connection control > 5.3.5 RRC reconnection "
        "> 5.3.5.3 Reception"
    )


def test_chunk_text_is_breadcrumb_then_body():
    chunk = build_chunks([clause()], SPEC, "17", 6000)[0]
    assert chunk.text.startswith(chunk.breadcrumb)
    assert chunk.text.endswith("The UE shall comply.")


def test_chunk_id_is_stable_and_unique():
    chunks = build_chunks([clause("5.3.5.3"), clause("5.3.5.4")], SPEC, "17", 6000)
    assert chunks[0].chunk_id == "38.331#5.3.5.3"
    assert len({c.chunk_id for c in chunks}) == 2


def test_oversized_clause_splits_on_paragraph_boundaries():
    body = "\n\n".join(f"Paragraph {i} with some text." for i in range(40))
    chunks = build_chunks([clause(body=body)], SPEC, "17", 300)
    assert len(chunks) > 1
    assert all(c.breadcrumb.endswith("5.3.5.3 Reception") for c in chunks)
    assert [c.chunk_id for c in chunks[:2]] == ["38.331#5.3.5.3/0", "38.331#5.3.5.3/1"]


def test_split_parts_never_lose_content():
    body = "\n\n".join(f"Paragraph {i}." for i in range(40))
    chunks = build_chunks([clause(body=body)], SPEC, "17", 300)
    recovered = " ".join(c.text.split(chunks[0].breadcrumb)[-1] for c in chunks)
    for i in range(40):
        assert f"Paragraph {i}." in recovered


def test_single_paragraph_longer_than_max_is_not_dropped():
    chunks = build_chunks([clause(body="x" * 5000)], SPEC, "17", 300)
    assert len(chunks) == 1
    assert "x" * 5000 in chunks[0].text


def test_repeated_clause_id_still_gets_a_unique_chunk_id():
    # TS 28.552 v17.17.0 really does number two different clauses 5.7.2.3.
    # Colliding chunk ids would silently overwrite one at index time.
    chunks = build_chunks(
        [clause("5.7.2.3", "Incoming", "a) incoming."),
         clause("5.7.2.3", "Outgoing", "a) outgoing.")],
        SPEC, "17", 6000,
    )
    assert [c.chunk_id for c in chunks] == ["38.331#5.7.2.3", "38.331#5.7.2.3~2"]
    assert chunks[1].clause_id == "5.7.2.3"


def test_repeated_clause_id_that_also_splits_stays_unique():
    body = "\n\n".join(f"Paragraph {i} with some text." for i in range(40))
    chunks = build_chunks(
        [clause("5.7.2.3", body=body), clause("5.7.2.3", body=body)], SPEC, "17", 300
    )
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert chunks[-1].chunk_id.startswith("38.331#5.7.2.3~2/")


def test_metadata_is_carried_onto_every_chunk():
    chunk = build_chunks([clause()], SPEC, "17", 6000)[0]
    assert (chunk.spec_id, chunk.version, chunk.release) == ("38.331", "17.5.0", "17")
    assert chunk.clause_id == "5.3.5.3"
