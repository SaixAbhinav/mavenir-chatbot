"""Parse a 3GPP .docx into Leaf Clauses.

A Leaf Clause is a numbered Clause carrying body text and no numbered
children. A Clause with both body and children contributes its own body as a
Leaf Clause; its children are separate Leaf Clauses. Leaf-only chunking means
no Chunk duplicates another's text, so every Citation is unambiguous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

# "5.3.5.3<tab>Reception of an RRCReconfiguration by the UE" (numbered clause)
# "5.1.1a<tab>Initialization of variables" (3GPP inserts a clause between two
# existing ones by suffixing a letter, so every dot-part may carry one)
# "A.3.1.1<tab>ASN.1 clauses" (annex clause: single leading letter followed by
# at least one dot-numeric part; a bare "A" is not a clause id on its own — it
# would false-positive-match ordinary headings like "A Note on Timer Handling",
# so annex containers are recognised by their banner instead, below)
_HEADING = re.compile(
    r"^([A-Z](?:\.\d+[a-z]?)+|\d+[a-z]?(?:\.\d+[a-z]?)*)[\t ]+(.+?)\s*$"
)

# "Annex G (informative):<newline>Change history" — the container heading for an
# annex. Its clause id is the letter. Recognised by the literal word rather than
# by shape, which is what keeps a bare "A" from matching ordinary prose.
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
            collected.append(current)   # ancestors were set when the Clause was created
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
                # Foreword, unnumbered sub-headings. Front matter before the
                # first real clause (current is None) stays out; once a clause
                # is open, stay a faithful reader and fold the text into its
                # body rather than discarding it.
                if current is not None:
                    body.append(text)
                continue
            clause_id, title = match
            close_current()
            # Keep only headings that are genuine ancestors of this clause id.
            # Prefix matching rather than depth arithmetic, because 3GPP
            # documents sometimes skip a level (5 straight to 5.3.5).
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
