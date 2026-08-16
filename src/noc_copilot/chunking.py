"""Turn Leaf Clauses into Chunks — a clause body prefixed with its breadcrumb,
which carries structural context and is itself retrievable text."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .clauses import Clause
from .config import SpecEntry


@dataclass
class Chunk:
    chunk_id: str
    spec_id: str
    version: str
    release: str
    clause_id: str
    clause_title: str
    breadcrumb: str
    text: str

    def metadata(self) -> dict[str, str]:
        return {
            "spec_id": self.spec_id,
            "version": self.version,
            "release": self.release,
            "clause_id": self.clause_id,
            "clause_title": self.clause_title,
            "breadcrumb": self.breadcrumb,
        }


def _breadcrumb(clause: Clause, spec: SpecEntry) -> str:
    trail = [f"{cid} {title}" for cid, title in clause.ancestors]
    trail.append(f"{clause.clause_id} {clause.title}")
    return f"TS {spec.spec_id} v{spec.version} § " + " > ".join(trail)


def _split_body(body: str, budget: int) -> list[str]:
    """Split on paragraph boundaries, never mid-paragraph — a mid-sentence cut
    would break supporting-quote matching. An over-long paragraph is emitted whole."""
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in body.split("\n\n"):
        if current and size + len(paragraph) > budget:
            parts.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        parts.append("\n\n".join(current))
    return parts


def build_chunks(
    clauses: list[Clause], spec: SpecEntry, release: str, max_chars: int
) -> list[Chunk]:
    chunks: list[Chunk] = []
    # Clause ids repeat in practice (TS 28.552 numbers two measurements 5.7.2.3),
    # so colliding ids are suffixed in document order (stable: versions are pinned).
    seen: Counter[str] = Counter()
    for clause in clauses:
        breadcrumb = _breadcrumb(clause, spec)
        budget = max(max_chars - len(breadcrumb) - 2, 1)
        parts = _split_body(clause.body, budget)
        seen[clause.clause_id] += 1
        occurrence = seen[clause.clause_id]
        base_id = f"{spec.spec_id}#{clause.clause_id}"
        if occurrence > 1:
            base_id = f"{base_id}~{occurrence}"
        for index, part in enumerate(parts):
            chunk_id = base_id if len(parts) == 1 else f"{base_id}/{index}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    spec_id=spec.spec_id,
                    version=spec.version or "",
                    release=release,
                    clause_id=clause.clause_id,
                    clause_title=clause.title,
                    breadcrumb=breadcrumb,
                    text=f"{breadcrumb}\n\n{part}",
                )
            )
    return chunks
