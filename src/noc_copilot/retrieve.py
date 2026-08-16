"""Hybrid retrieval: dense + BM25, fused by RRF for ordering only.

RRF must never gate — it consumes ranks, so its top score is identical whether
the best hit is a perfect match or the least-irrelevant chunk; Gate 1 reads the
raw cosine/BM25 kept on each Hit. Dense search is exact (the corpus is small).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .store import embed_texts, load_collection

_TOKEN = re.compile(r"[a-z0-9]+")
CANDIDATES = 50


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _parent(clause_id: str) -> str:
    """The clause id one level up. A top-level clause is its own parent."""
    return clause_id.rsplit(".", 1)[0] if "." in clause_id else clause_id


@dataclass
class Hit:
    chunk_id: str
    clause_id: str
    spec_id: str
    version: str
    breadcrumb: str
    text: str
    cosine: float
    bm25: float
    rrf: float
    # Added by sibling expansion, not ranked in (rrf 0.0); Gate 1 reads ranked
    # Hits only.
    expanded: bool = False

    def citation(self) -> str:
        return f"TS {self.spec_id} v{self.version} §{self.clause_id}"


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


class Retriever:
    def __init__(self, index_dir: Path, model_name: str) -> None:
        self.model_name = model_name
        self.collection = load_collection(Path(index_dir))
        payload = self.collection.get(include=["documents", "metadatas", "embeddings"])
        self.ids: list[str] = payload["ids"]
        self.documents: list[str] = payload["documents"]
        self.metadatas: list[dict] = payload["metadatas"]
        # Normalised at index time, so a dot product is the cosine.
        self.embeddings = np.asarray(payload["embeddings"], dtype=np.float32)
        self._position = {cid: i for i, cid in enumerate(self.ids)}
        self._bm25 = BM25Okapi([tokenize(d) for d in self.documents])
        # (spec_id, parent clause id) -> chunk ids, for sibling expansion.
        self._family: dict[tuple[str, str], list[str]] = defaultdict(list)
        for cid, meta in zip(self.ids, self.metadatas):
            self._family[(meta["spec_id"], _parent(meta["clause_id"]))].append(cid)

    def search(
        self,
        query: str,
        top_k: int,
        per_spec_cap: int | None = None,
        sibling_expand_from: int = 1,
        sibling_cap: int = 4,
    ) -> list[Hit]:
        embedding = np.asarray(embed_texts([query], self.model_name)[0], dtype=np.float32)
        cosines = self.embeddings @ embedding
        candidates = min(CANDIDATES, len(self.ids))
        dense_order = np.argsort(-cosines)[:candidates]
        dense_ids = [self.ids[i] for i in dense_order]

        bm25_scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(self.ids)), key=lambda i: bm25_scores[i], reverse=True)
        sparse_ids = [self.ids[i] for i in ranked[:candidates]]

        fused = rrf_fuse([dense_ids, sparse_ids])
        ordered = sorted(fused, key=lambda cid: fused[cid], reverse=True)

        # Cap per specification so one spec (e.g. TS 28.552's 733 near-identical
        # measurement clauses) cannot fill the whole context.
        cap = per_spec_cap if per_spec_cap is not None else len(self.ids)
        best: list[str] = []
        taken: dict[str, int] = defaultdict(int)
        for cid in ordered:
            spec = self.metadatas[self._position[cid]]["spec_id"]
            if taken[spec] < cap:
                best.append(cid)
                taken[spec] += 1
            if len(best) == top_k:
                break

        # Leaf-clause chunking splits procedures across siblings; add neighbours
        # of the top hits after ranking, marked and never reordered ahead.
        chosen = set(best)
        extra: list[str] = []
        for cid in best[:sibling_expand_from]:
            meta = self.metadatas[self._position[cid]]
            for sibling in self._family[(meta["spec_id"], _parent(meta["clause_id"]))]:
                if sibling not in chosen and sibling not in extra:
                    extra.append(sibling)
        extra = extra[:sibling_cap]

        # Carry both raw scores on every Hit, so a BM25-only hit does not enter
        # Gate 1 with cosine 0.0 and get refused on a score it never earned.
        hits = []
        for cid in best + extra:
            index = self._position[cid]
            meta = self.metadatas[index]
            hits.append(Hit(
                chunk_id=cid,
                clause_id=meta["clause_id"],
                spec_id=meta["spec_id"],
                version=meta["version"],
                breadcrumb=meta["breadcrumb"],
                text=self.documents[index],
                cosine=float(cosines[index]),
                bm25=float(bm25_scores[index]),
                rrf=fused.get(cid, 0.0) if cid in chosen else 0.0,
                expanded=cid not in chosen,
            ))
        return hits
