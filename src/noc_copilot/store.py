"""Embedding and the persisted ChromaDB collection."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

COLLECTION = "clauses"


@lru_cache(maxsize=2)
def _model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], model_name: str) -> list[list[float]]:
    vectors = _model(model_name).encode(
        texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False
    )
    return [v.tolist() for v in vectors]


def build_index(chunks, index_dir: Path, model_name: str) -> None:
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(index_dir))
    if COLLECTION in {c.name for c in client.list_collections()}:
        client.delete_collection(COLLECTION)
    # Cosine space so that raw_cosine = 1 - distance in retrieve.py.
    collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    for start in range(0, len(chunks), 256):
        batch = chunks[start : start + 256]
        collection.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[c.metadata() for c in batch],
            embeddings=embed_texts([c.text for c in batch], model_name),
        )


def load_collection(index_dir: Path):
    client = chromadb.PersistentClient(path=str(Path(index_dir)))
    return client.get_collection(COLLECTION)
