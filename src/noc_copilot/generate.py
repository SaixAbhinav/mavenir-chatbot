"""Grounded generation. Temperature 0 everywhere for reproducibility;
evaluate.py passes allow_failover=False so a rate limit fails loudly."""
from __future__ import annotations

import json
import os
import time

from .config import Settings
from .prompts import build_prompt
from .schemas import Answer

__all__ = ["build_prompt", "generate", "GenerationError"]

# Retry the same model on transient errors. Failover can't cover a 503 (Groq's
# 8k-token cap rejects the ~12k prompt) and would break single-model evals.
RETRY_DELAYS = (2.0, 5.0)
_TRANSIENT = ("503", "429", "unavailable", "overloaded", "high demand",
              "rate limit", "timeout", "deadline")


class GenerationError(RuntimeError):
    pass


def _sleep(seconds: float) -> None:      # seam for tests
    time.sleep(seconds)


def _is_transient(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT)


def _gemini(prompt: str, model: str) -> Answer:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=Answer,
        ),
    )
    return Answer.model_validate_json(response.text)


def _strict_schema() -> dict:
    """Answer's JSON Schema tightened for Groq strict mode: additionalProperties
    false and every property required on every object, or Groq returns a 400."""
    def tighten(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"])
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for value in node:
                tighten(value)

    schema = Answer.model_json_schema()
    tighten(schema)
    return schema


def _groq(prompt: str, model: str) -> Answer:
    from groq import Groq

    schema = _strict_schema()
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": schema, "strict": True},
        },
    )
    return Answer.model_validate(json.loads(response.choices[0].message.content))


def generate(
    question: str,
    hits,
    settings: Settings,
    provider: str = "gemini",
    allow_failover: bool = True,
) -> tuple[Answer, str]:
    prompt = build_prompt(question, hits)
    order = [provider] + ([p for p in ("gemini", "groq") if p != provider] if allow_failover else [])
    errors = []
    for name in order:
        model = settings.gemini_model if name == "gemini" else settings.groq_model
        if not model:
            errors.append(f"{name}: no model id configured")
            continue
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                call = _gemini if name == "gemini" else _groq
                return call(prompt, model), model
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                # Transient errors are worth waiting out; a schema/key error is not.
                if attempt == len(RETRY_DELAYS) or not _is_transient(exc):
                    break
                _sleep(RETRY_DELAYS[attempt])
    raise GenerationError("; ".join(errors))
