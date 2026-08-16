"""FastAPI service.

Rate caps exist because the hosted Space is public and holds the API key.
Past a cap the API explains itself rather than surfacing a provider error.
"""
from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from .config import load_settings, load_specs
from .generate import GenerationError
from .pipeline import Pipeline

load_dotenv()
REPO = Path(__file__).resolve().parents[2]

app = FastAPI(title="3GPP NOC Copilot")


class ChatRequest(BaseModel):
    question: str
    session_id: str = "anonymous"

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be empty")
        return value.strip()


@app.on_event("startup")
def startup() -> None:
    settings = load_settings(REPO / "config" / "settings.yaml")
    app.state.settings = settings
    app.state.corpus = load_specs(REPO / "config" / "specs.yaml")
    app.state.pipeline = Pipeline(REPO / "data" / "index", settings)
    app.state.used = {}
    app.state.total = 0


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    settings = app.state.settings
    used = app.state.used.get(request.session_id, 0)
    if used >= settings.session_cap or app.state.total >= settings.daily_cap:
        raise HTTPException(
            status_code=429,
            detail="Demo query limit reached. Clone the repository and run it locally "
                   "with your own API key — see the README.",
        )
    app.state.used[request.session_id] = used + 1
    app.state.total += 1
    try:
        result = app.state.pipeline.answer(request.question)
    except GenerationError as exc:
        raise HTTPException(status_code=503, detail=f"No LLM provider available: {exc}")
    return {
        "answer": result.answer,
        "refused": result.refused,
        "refusal_reason": result.refusal_reason,
        "gate": result.gate,
        "citations": result.citations,
        "model_id": result.model_id,
        "latency_ms": result.latency_ms,
    }


@app.get("/health")
def health() -> dict:
    manifest_path = REPO / "data" / "index" / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    try:
        chunks = app.state.pipeline.retriever.collection.count()
        status = "ok"
    except Exception:
        chunks, status = 0, "index_unavailable"
    return {
        "status": status,
        "chunks": chunks,
        "release": manifest.get("release"),
        "gemini_model": app.state.settings.gemini_model,
        "groq_model": app.state.settings.groq_model,
    }
