"""Ingest: download -> normalise -> parse -> chunk -> index.

Runs locally only. The built index (data/index/) is git-ignored — it holds
copyrighted 3GPP clause text — so each environment regenerates it from these
downloads before running the app.
"""
from __future__ import annotations

import json
from pathlib import Path

from .acquire import download_spec, extract_document, normalise_to_docx
from .chunking import build_chunks
from .clauses import Clause, parse_leaf_clauses
from .config import load_settings, load_specs

REPO = Path(__file__).resolve().parents[2]
RAW, NORMALISED, INDEX = REPO / "data" / "raw", REPO / "data" / "normalised", REPO / "data" / "index"


def drop_excluded(clauses: list[Clause], exclude: list[str]) -> list[Clause]:
    """Remove Clauses inside an excluded branch of the document.

    Scope is configuration, never the parser. Matching is on whole
    clause-id parts, so excluding "6" drops 6 and 6.3.2 but leaves 60.1 alone.
    """
    if not exclude:
        return clauses
    prefixes = [tuple(e.split(".")) for e in exclude]
    kept = []
    for clause in clauses:
        parts = tuple(clause.clause_id.split("."))
        if not any(parts[: len(p)] == p for p in prefixes):
            kept.append(clause)
    return kept


def main() -> None:
    from .store import build_index  # imported late; heavy dependency

    corpus = load_specs(REPO / "config" / "specs.yaml")
    settings = load_settings(REPO / "config" / "settings.yaml")
    if corpus.release is None:
        raise SystemExit("No release pinned. Run scripts/discover_versions.py first.")

    all_chunks, manifest = [], []
    for spec in corpus.specs:
        archive = download_spec(spec, RAW)
        raw_doc = extract_document(archive, RAW)
        document = normalise_to_docx(raw_doc, NORMALISED)
        parsed = parse_leaf_clauses(document)
        clauses = drop_excluded(parsed, spec.exclude_clauses)
        chunks = build_chunks(clauses, spec, str(corpus.release), settings.max_chunk_chars)
        all_chunks.extend(chunks)
        manifest.append({
            "spec_id": spec.spec_id, "version": spec.version,
            "source_format": raw_doc.suffix, "leaf_clauses": len(clauses),
            "excluded_clauses": len(parsed) - len(clauses),
            "exclude_rules": spec.exclude_clauses,
            "chunks": len(chunks),
        })
        print(f"{spec.spec_id} v{spec.version} [{raw_doc.suffix}]: "
              f"{len(clauses)} clauses ({len(parsed) - len(clauses)} excluded) "
              f"-> {len(chunks)} chunks")

    # The Change history annexes are editorial metadata, not specification text.
    # Assert rather than trust the exclusion lists.
    leaked = [c.chunk_id for c in all_chunks if "change history" in c.clause_title.lower()]
    if leaked:
        raise SystemExit(f"Change history reached the corpus: {leaked}")

    build_index(all_chunks, INDEX, settings.embedding_model)
    (INDEX / "manifest.json").write_text(
        json.dumps({"release": corpus.release, "total_chunks": len(all_chunks),
                    "specs": manifest}, indent=2), encoding="utf-8")
    print(f"\nIndexed {len(all_chunks)} chunks from {len(corpus.specs)} specs.")


if __name__ == "__main__":
    main()
