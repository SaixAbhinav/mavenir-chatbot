"""Typed loading of the corpus definition and runtime settings."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class SpecEntry(BaseModel):
    spec_id: str
    series: str
    title: str
    role: str
    version: str | None = None
    # Branches of the document kept out of the indexed corpus: ASN.1 sections
    # (ADR 0005) and the Change history annex (ADR 0006). Applied at ingest,
    # never by the parser.
    exclude_clauses: list[str] = []


class CorpusConfig(BaseModel):
    release: str | None = None
    specs: list[SpecEntry]


class Settings(BaseModel):
    embedding_model: str
    gemini_model: str | None = None
    groq_model: str | None = None
    top_k: int
    max_chunk_chars: int
    # Retrieval shaping, measured in findings §4.20. per_spec_cap keeps one
    # specification from filling the whole context; sibling expansion completes
    # a procedure that leaf-clause chunking split across sibling clauses.
    per_spec_cap: int = 4
    sibling_expand_from: int = 1
    sibling_cap: int = 4
    cosine_threshold: float | None = None
    bm25_threshold: float | None = None
    session_cap: int
    daily_cap: int


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_specs(path: Path) -> CorpusConfig:
    return CorpusConfig.model_validate(_read_yaml(Path(path)))


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(_read_yaml(Path(path)))
