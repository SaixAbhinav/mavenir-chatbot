# 3GPP NOC Copilot

A grounded question-answering assistant over a fixed corpus of 3GPP specifications. It
answers with an exact clause citation or explicitly declines. This file is the glossary —
it defines what the words mean here, and nothing else.

## Corpus structure

**Corpus**:
The seven Specifications the assistant can answer from, all pinned to a single Release.
Fixed at build time; the assistant has no knowledge outside it.

**Release**:
The 3GPP release the whole Corpus is pinned to. One Release across all Specifications, so
that a cross-Specification answer describes a single coherent version of the system.
Clause Ids move between Releases, so a Citation is only meaningful with its version.

**Specification**:
A single 3GPP standards document, identified by its 3GPP number (`TS 38.331`) and a pinned
version. Never referred to by its ETSI number in citations.
_Avoid_: spec sheet, standard, document

**Clause**:
A numbered, titled section of a Specification (`5.3.5.3`). Clauses nest. Every Clause has
exactly one Clause Id within its Specification.
_Avoid_: section, chapter, heading, paragraph

**Leaf Clause**:
A Clause that has body text and no numbered child Clauses. The only kind of Clause that
becomes a Chunk. A Clause with both body text and children contributes its own body as a
Leaf Clause; its children are separate Leaf Clauses.

**Breadcrumb**:
The ordered chain of ancestor Clause titles prepended to a Chunk
(`TS 38.331 § 5.3 Connection control > 5.3.5 RRC reconnection > 5.3.5.3 Reception of an
RRCReconfiguration by the UE`). Carries structural context into a Chunk that may not
contain its parents' terminology, and is itself retrievable text.

**Chunk**:
The unit of retrieval: exactly one Leaf Clause's body plus its Breadcrumb. Chunks never
overlap and never duplicate body text, so a Chunk has exactly one identity.
_Avoid_: passage, segment, node, document (in the vector-store sense)

## Answering

**Refusal**:
A deliberate, successful outcome in which the assistant declines to answer and says why. A
Refusal is never an error and is never a fallback — it is the correct response whenever
grounding cannot be established.
_Avoid_: failure, rejection, no-answer, I-don't-know

**Refusal Reason**:
Which condition produced a Refusal. The four are distinct and are reported separately,
because they mean different things to the reader and are caught by different Gates:
*no relevant Clause* (nothing in the Corpus covers this), *insufficient* (on-topic Clauses
that do not contain the fact asked for), *not answerable from standards* (a question about
a live network, which no Specification can answer), and *unverifiable* (the answer's
Supporting Quote could not be found in the cited Chunk).

**Relevance Gate**:
A check that can produce a Refusal. Gates are independent and each catches a different
failure. Ordering signals (Reciprocal Rank Fusion) are never Gates — fused ranks carry no
absolute relevance and cannot distinguish a good match from the best of a bad corpus.

**Citation**:
A reference from an answer to a Clause it drew on, rendered with the 3GPP Specification
number, pinned version and Clause Id (`TS 38.331 v17.5.0 §5.3.5.3`). A Citation is valid
only if that Clause was actually retrieved for this question.

**Supporting Quote**:
A verbatim span of a cited Chunk that the answer rests on, checked in code to appear
literally in that Chunk. Distinguishes "the citation is real" from "the claim is anchored
to text that provably exists in the Specification".
_Avoid_: evidence, snippet, excerpt

**Groundedness**:
Whether an answer's claims actually follow from the Chunks it cites. Measured offline
during evaluation, never asserted as a runtime guarantee.
_Avoid_: accuracy, correctness, faithfulness

**Sufficiency**:
Whether the retrieved Chunks actually contain the answer, as distinct from being on-topic.
Judged by the model, because no similarity score can detect an on-topic Chunk that omits
the specific fact asked for.

## Evaluation

**Eval Question**:
A question with a known expected outcome, authored by reading a Specification and frozen
before any retrieval tuning. Never generated from a Chunk — questions derived from Chunk
text leak the Chunk's vocabulary and make retrieval look better than it is.

**Gold Clause Id**:
The Clause that answers an Eval Question, established by reading the Specification. Never
taken from system output. Once committed, an Eval Question is never rewritten after seeing
it fail — questions may only be added.
