# Chunk on leaf clauses only, with ancestor breadcrumbs

3GPP specifications are deeply nested numbered clauses, so "one chunk per clause" is
ambiguous. We chunk only **leaf clauses** — numbered clauses with body text and no numbered
children — and prepend each chunk with the ordered chain of its ancestors' titles. A clause
carrying both body text and children contributes its own body as a leaf; its children are
separate leaves.

The deciding property is that **a chunk has exactly one identity**. No chunk duplicates
another's text, so a citation is unambiguous, an eval question's gold clause id is
unambiguous, and no deduplication step is needed.

## Considered options

**Parent-inclusive chunking** — every numbered heading becomes a chunk containing its own
text plus all descendants. Rejected: the same sentence would exist at three or four nesting
depths, so retrieval returns near-duplicates, the context window fills with repeats, and
recall@k is inflated by counting one passage several times.

**Leaf clauses with no breadcrumb.** Rejected: a leaf titled "General" carries almost no
retrievable signal alone, and the model loses the framing its parent provides. The
breadcrumb also injects parent terminology into a chunk that may not contain those words,
which measurably helps retrieval.

## Consequences

**This is the expensive decision to reverse.** Re-chunking changes chunk boundaries, which
invalidates the gold clause ids in the frozen eval set — and those may not be rewritten
(see `eval/questions.yaml`). Reversing means re-authoring evaluation questions, not just
re-running ingest.

**Procedures split across sibling clauses.** A 3GPP procedure written across `5.3.5.1`–
`5.3.5.4` arrives as four separate chunks, so an answer can be correctly cited,
verbatim-anchored and still incomplete. No gate detects this. Mitigated by `top_k = 8`;
sibling expansion is deliberately unbuilt pending eval evidence.
