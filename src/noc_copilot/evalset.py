"""The frozen evaluation question set."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class EvalQuestion:
    id: str
    question: str
    expect: str                    # "answer" | "refuse"
    kind: str | None = None        # single | cross | noc | paraphrase
    gold: list[str] = None         # ["38.331#5.3.5.3", ...]
    reason: str | None = None      # for expect == "refuse"

    def __post_init__(self) -> None:
        self.gold = self.gold or []


def load_questions(path: Path) -> list[EvalQuestion]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [EvalQuestion(**entry) for entry in raw["questions"]]
