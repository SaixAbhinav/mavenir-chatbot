# Annex banners are Clauses; their letter is the clause id

An annex begins with a banner heading — `Annex G (informative):` followed by a line break and
a title. It carries no dot-numeric clause id, so it failed the heading pattern, and under the
faithful-reader rule ([§4.7](../findings.md)) its content folded into whichever Leaf Clause
was last open.

That content is not small. Every 3GPP document ends with an `Annex X (informative): Change
history` banner and a revision table — 384 rows in TS 38.300, 139,933 characters in TS 38.331,
about 261,000 characters across the corpus. All of it was being attributed to a real clause:
TS 38.321 §7.4 *PRACH Mask Index values* carried 41,708 characters of CR numbers and meeting
ids as if they were its text. Annex prose sitting above the first numbered sub-clause
(TS 38.300 Annex C, 1,763 characters) was mis-attributed the same way.

**An annex banner is therefore parsed as a Clause whose id is its letter.** `Annex C` becomes
clause `C`, and `C.1` records it as an ancestor, so annex breadcrumbs finally name the annex
they belong to.

## Why the letter is safe here but not in the pattern

[§4.6](../findings.md) established that a bare letter cannot be a clause id in the heading
pattern: `A Note on Timer Handling` would parse as clause `A` and misfile real content. That
still holds. The banner is matched on the **literal word `Annex`**, not on shape, so the
false-positive surface is a heading that genuinely begins "Annex X" — which is a banner. A
regression test covers `Annexes referenced by this clause`.

## Considered options

**Close the open clause at a banner and discard until the next numbered heading.** Simpler,
and it stops the mis-attribution. Rejected because it silently drops about 4,500 characters of
genuine annex prose, and because it makes the parser decide what belongs in the corpus —
exactly what [ADR 0005](0005-exclude-asn1-from-corpus.md) rules out.

**Special-case the words "Change history".** Rejected for the same reason: the parser would be
encoding a corpus-scope decision. Scope is configuration.

## Consequences

The Change history annex is now a Clause of its own rather than a contaminant, and is removed
from the corpus the same way ASN.1 is — a per-specification `exclude_clauses` entry applied at
ingest (Task 7). The ids are `38.300: G`, `38.331: E`, `38.323: C`, `38.322: A`, `38.321: A`,
`28.545: A`, `28.552: B`.

Citations of the form `TS 38.300 §C` are now possible. This is correct — Annex C is a citable
unit of the document — and annex sub-clause citations are unchanged.
