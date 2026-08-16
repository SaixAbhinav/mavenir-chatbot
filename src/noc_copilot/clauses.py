"""Parse a 3GPP .docx into Leaf Clauses — numbered clauses with body text and no
numbered children. A clause with both body and children yields its own body as a
leaf plus its children as separate leaves, so no Chunk duplicates another."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph


_HEADING = re.compile(
    r"^([A-Z](?:\.\d+[a-z]?)+|\d+[a-z]?(?:\.\d+[a-z]?)*)[\t ]+(.+?)\s*$"
)

# Annex container heading, e.g. "Annex G (informative): Change history"; clause id
# is the letter. Matched by the literal word so a bare "A" in prose doesn't match.
_ANNEX_BANNER = re.compile(
    r"^Annex[\t ]+([A-Z])\b[\t ]*(?:\([^)]*\))?[\t ]*:?\s*(.*)$", re.DOTALL
)


@dataclass
class Clause:
    clause_id: str
    title: str
    body: str = ""
    ancestors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return self.clause_id.count(".") + 1


def _match_heading(text: str) -> tuple[str, str] | None:
    """A heading's (clause_id, title), or None if it names no clause."""
    match = _HEADING.match(text)
    if match is not None:
        return match.group(1), match.group(2)
    banner = _ANNEX_BANNER.match(text)
    if banner is not None:
        letter = banner.group(1)
        title = " ".join(banner.group(2).split())
        return letter, title or f"Annex {letter}"
    return None


def _is_heading(paragraph: Paragraph) -> bool:
    return (paragraph.style.name or "").lower().startswith("heading")


def _table_to_markdown(table: Table) -> str:
    rows = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
    if not rows:
        return ""
    header, *rest = rows
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rest]
    return "\n".join(lines)


def _iter_blocks(document) -> list[Paragraph | Table]:
    """Paragraphs and tables in document order."""
    from docx.oxml.ns import qn
    blocks: list[Paragraph | Table] = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(Paragraph(child, document))
        elif child.tag == qn("w:tbl"):
            blocks.append(Table(child, document))
    return blocks


def parse_leaf_clauses(docx_path: Path) -> list[Clause]:
    document = docx.Document(str(docx_path))
    collected: list[Clause] = []
    stack: list[Clause] = []          # headings seen, filtered to true ancestors
    current: Clause | None = None
    body: list[str] = []

    def close_current() -> None:
        nonlocal current, body
        if current is None:
            return
        current.body = "\n\n".join(part for part in body if part).strip()
        if current.body:
            collected.append(current)
        current, body = None, []

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            if current is not None:
                body.append(_table_to_markdown(block))
            continue

        text = block.text.strip()
        if not text:
            continue

        if _is_heading(block):
            match = _match_heading(text)
            if match is None:
                # Unnumbered heading: drop it before the first clause, fold it
                # into the open clause's body once one is open.
                if current is not None:
                    body.append(text)
                continue
            clause_id, title = match
            close_current()
            # Keep only genuine ancestors (prefix match, not depth arithmetic —
            # 3GPP docs sometimes skip a level, e.g. 5 → 5.3.5).
            stack = [c for c in stack if clause_id.startswith(c.clause_id + ".")]
            current = Clause(
                clause_id=clause_id,
                title=title,
                ancestors=[(c.clause_id, c.title) for c in stack],
            )
            stack.append(current)
        elif current is not None:
            body.append(text)

    close_current()
    return collected
