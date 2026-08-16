# Exclude ASN.1 information-element sections from the corpus

3GPP protocol specifications carry their information elements as flat ASN.1 blocks with no
numbered subheadings, so leaf-clause parsing yields a handful of enormous clauses — in
TS 38.331 v17.17.0, clause 6.3.2 alone is **1,133,789 characters**, with 6.3.3 at 410,148
and 6.2.2 at 261,509. Across the specification, 54 clauses exceed the 6,000-character chunk
ceiling and would produce roughly **530 chunks sharing a handful of identical breadcrumbs**.

That silently defeats the property [ADR 0001](0001-leaf-clause-chunking.md) is built on: a
chunk has exactly one identity. A citation reading `TS 38.331 §6.3.2` would point at over a
million characters, which is not a reference. We therefore exclude ASN.1 sections from the
indexed corpus, via a per-specification `exclude_clauses` list in `config/specs.yaml`
applied during ingest.

The parser is deliberately **not** changed. `clauses.py` stays a faithful reader of whatever
the document contains; corpus scope is a configuration decision, and mixing the two would
make the parser's behaviour depend on what we happen to want indexed today.

## Considered options

**Split ASN.1 on `Name ::= SEQUENCE {` boundaries**, making each information element its own
chunk cited as `6.3.2/RRCReconfiguration`. Genuinely better — it is how engineers refer to
these — and it remains the right long-term answer. Rejected for now on cost: it is new code
and tests on a four-day deadline, taken out of the day reserved for authoring the evaluation
set, which is the submission's primary evidence.

**Leave the oversized clauses in.** Rejected: grounding would still hold, because quote
anchoring is per-chunk, but citation precision would collapse across the largest section of
the flagship specification.

## Consequences

**The assistant cannot answer questions about ASN.1 field definitions** — "what fields does
`RRCReconfiguration` contain?" is outside the corpus and should be refused, not guessed.
This is a declared boundary, stated in the README, not an accident.

**This is a good trade for the intended audience.** The questions a NOC copilot serves —
procedures, timers, triggers, alarms, counters — live in clause 5 of the protocol specs and
in the 28-series management specifications, none of which are affected. Excluding ASN.1
removes roughly 2M characters of machine-readable schema that prose-oriented retrieval
handles poorly, which sharpens the rest of the index.

**Evaluation questions must respect the boundary.** No gold clause id may fall inside an
excluded range, and it is worth including an ASN.1 question among the out-of-scope set to
prove the refusal works.

ASN.1-aware chunking is recorded as future work.
