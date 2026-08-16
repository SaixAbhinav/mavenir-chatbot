from noc_copilot.chunking import Chunk
from noc_copilot.store import build_index, load_collection


def make_chunk(cid, text):
    return Chunk(
        chunk_id=cid, spec_id="38.331", version="17.5.0", release="17",
        clause_id=cid.split("#")[1], clause_title="T", breadcrumb="B", text=text,
    )


def test_index_roundtrips_chunks_and_metadata(tmp_path):
    chunks = [
        make_chunk("38.331#5.3.5.3", "The UE shall re-establish the connection."),
        make_chunk("38.331#5.3.5.4", "Secondary cell group failure handling."),
    ]
    build_index(chunks, tmp_path, "BAAI/bge-small-en-v1.5")
    collection = load_collection(tmp_path)
    assert collection.count() == 2
    got = collection.get(ids=["38.331#5.3.5.3"], include=["documents", "metadatas"])
    assert got["documents"][0].startswith("The UE shall")
    assert got["metadatas"][0]["clause_id"] == "5.3.5.3"


def test_collection_uses_cosine_distance(tmp_path):
    build_index([make_chunk("38.331#1", "text")], tmp_path, "BAAI/bge-small-en-v1.5")
    collection = load_collection(tmp_path)
    assert collection.metadata["hnsw:space"] == "cosine"
