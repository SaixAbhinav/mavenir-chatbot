# Design — 3GPP NOC Chatbot

A design document for a question-answering assistant over a fixed corpus of 3GPP
5G specifications. It explains *what was built and why each decision was made*.
For setup and how to run it, see [`README.md`](README.md).

---

## 1. Problem and design goal

A network-operations engineer needs to ask precise questions about the 5G NR
radio stack, fault supervision, and performance measurements, and get an answer
they can trust and cite. A general chatbot fails this task in a specific way: it
**hallucinates** — it will answer confidently whether or not it actually knows,
and a plausible-but-wrong answer about a standard is worse than no answer,
because the reader cannot tell it is wrong.

The single design goal follows from that: **make a confident, wrong answer
structurally hard to produce, not merely unlikely.** Everything below is in
service of it. The system answers only from the corpus, cites the exact clause,
and refuses whenever grounding cannot be established — a refusal is a correct
outcome, not a failure.

---

## 2. Architecture at a glance

The pipeline is deliberately explicit — no LangChain, LlamaIndex, or agent
framework — so every step is inspectable and every failure mode is owned in
code.

```
question
  → Retrieve         hybrid dense + BM25, fused by RRF, shaped for diversity
  → Gate 1           relevance — refuse on raw scores, before any model call
  → Generate         Gemini, temperature 0, structured JSON (Pydantic schema)
  → Gate 2           sufficiency — model declares context adequate / in-scope
  → Gate 3           verifiability — every quote must appear verbatim in-code
  → answer + citations   (or a refusal, with one of four reasons)
```

Two surfaces sit on top: a **FastAPI** service (`/chat`, `/health`) holds all
logic, and a thin **Streamlit** client renders it — no logic lives in the UI, so
the pipeline is testable without a browser.

Module layout (`src/noc_copilot/`):

| Module | Responsibility |
|--------|----------------|
| `acquire.py`, `versions.py` | download specs from the 3GPP archive; pin versions |
| `clauses.py` | parse a `.docx` into leaf clauses (body + ancestry) |
| `chunking.py` | one leaf clause + breadcrumb → one chunk |
| `store.py` | embed and persist the ChromaDB collection |
| `retrieve.py` | hybrid retrieval, RRF fusion, per-spec cap, sibling expansion |
| `guards.py` | the three deterministic gates |
| `generate.py` | grounded generation with retry/failover |
| `pipeline.py` | wires retrieve → gates → generate together |
| `api.py` | FastAPI service |

---

## 3. Corpus and ingestion

Seven specifications, **all pinned to Release 17** so a cross-specification
answer describes one coherent version of the system: TS 38.300 (NR overall),
38.321 (MAC), 38.322 (RLC), 38.323 (PDCP), 38.331 (RRC), 28.545 (fault
supervision), 28.552 (performance measurements). Indexed into **2,085 chunks**.

Decisions:

- **Leaf-clause parsing, not fixed-size windows.** A 3GPP clause is the natural
  unit of meaning and of citation. The parser walks the `.docx` structure and
  emits each numbered leaf clause with its ancestry, so a chunk maps to exactly
  one clause id that can be cited back to the reader.
- **ASN.1 information-element sections are excluded.** They are enormous,
  near-duplicate, and defeat one-chunk-one-identity. Change-history annexes are
  excluded too (editorial metadata), and ingestion *asserts* none leaked rather
  than trusting the exclusion list. Other annexes are kept.
- **Exclusion scope is configuration, never the parser** (`config/specs.yaml`),
  matched on whole clause-id parts so excluding `6` drops `6.3.2` but not `60.1`.
- **The built index is not committed.** It contains copyrighted 3GPP clause
  text, so `data/` is git-ignored and regenerated locally via the ingest
  pipeline. Retrieved text is only ever shown as short, cited quotations.

---

## 4. Chunking

Each chunk is a clause body prefixed with its **breadcrumb** — the full
`TS 38.331 v17.17.0 § 5.3 > 5.3.10 > 5.3.10.3 …` trail. The breadcrumb is itself
retrievable text, so structural context (which protocol, which procedure) helps
a query match even when the clause body is terse.

- **Split only on paragraph boundaries, never mid-sentence.** A mid-sentence cut
  would break the verbatim-quote check in Gate 3, which is the backbone of the
  whole anti-hallucination guarantee. An over-long paragraph is emitted whole.
- **Colliding clause ids are suffixed in document order.** Real specs reuse ids
  (TS 28.552 numbers two measurements `5.7.2.3`); pinned versions make document
  order stable, so the suffixing is deterministic.

---

## 5. Retrieval

Two searches, fused, then shaped.

- **Hybrid dense + BM25.** Dense (BGE-small, cosine) catches paraphrases; BM25
  catches exact identifiers a NOC engineer actually types — timer names,
  counters, `periodicBSR-Timer`. Neither alone is enough.
- **Exact dense search, not ANN.** The corpus is ~2k chunks, so a brute-force
  dot product over normalised embeddings is fast and gives *exact* recall — no
  approximate-index recall loss. ChromaDB is used for persistence and metadata.
- **RRF fuses for ordering only — it never gates.** This is the subtle decision.
  Reciprocal Rank Fusion consumes *ranks*, so its top score is identical whether
  the best hit is a perfect match or the least-irrelevant chunk in the corpus.
  Using it as a relevance signal would be a bug. So each hit carries its **raw**
  cosine and BM25 scores, and Gate 1 thresholds those instead.
- **Per-spec cap.** One specification (TS 28.552 has hundreds of near-identical
  measurement clauses) must not fill the whole context, so at most *N* ranked
  chunks per spec are kept — preserving cross-specification coverage.
- **Sibling expansion.** Leaf-clause chunking can split a procedure across
  sibling clauses. After ranking, neighbours of the top hits are appended,
  marked as expanded and never reordered ahead of ranked hits (and never fed to
  Gate 1), so a split procedure is reassembled without polluting the relevance
  signal. Result: ~11 chunks of context.

---

## 6. Preventing hallucination — the core of the design

Rather than one safeguard, each way a hallucination could arise is closed by a
distinct mechanism. **Three deterministic gates sit outside the language model,
so none of them can be talked out of a refusal.**

| How a hallucination would arise | What blocks it |
|---------------------------------|----------------|
| Answering from the model's own training knowledge | The prompt supplies only the retrieved clauses and forbids outside knowledge; generation runs at temperature 0. |
| Answering when nothing on-topic was retrieved | **Gate 1 (relevance)** refuses on raw cosine/BM25, *before any model call* — cheap and model-independent. |
| Padding a thin or off-target context into a confident answer | **Gate 2 (sufficiency)** requires the model to declare the context sufficient, and to flag live-network questions the standards cannot answer. |
| Inventing a clause id, or paraphrasing / fabricating a quote | **Gate 3 (verifiability)** checks *in code* that every supporting quote appears **verbatim** (whitespace/case-normalised) in the clause it cites. A fabricated or altered citation is rejected and withheld, not shown. |
| A quote that is real but does not actually support the answer | Offline evaluation judges groundedness with a **different model** than the generator, so the check is independent of the thing it grades. |

**The four refusal reasons are reported separately** — *no relevant clause*,
*insufficient*, *not answerable from the standards* (a live-network question),
and *unverifiable* — because they mean different things to a NOC reader.

**Structured output.** The model must return a Pydantic-typed object
(`answer`, `sufficient`, `answerable_from_standards`, `citations[]`), enforced
via the provider's JSON-schema mode. This makes Gates 2 and 3 mechanical rather
than a matter of parsing prose.

**One bounded retry.** A verbatim-quote failure triggers exactly one re-prompt
("copy the quote character-for-character") before refusing. Insufficient and
live-network verdicts are *not* retried — they will not change on a re-ask.

---

## 7. Generation

- **Temperature 0 everywhere** for reproducibility.
- **Gemini (`gemini-3.7-flash`) is the generator**, chosen by measuring
  verbatim-quote adherence — an earlier model spliced two bullet points into one
  quote and failed Gate 3.
- **Groq (`gpt-oss-120b`) is the evaluation judge, not a generation failover.**
  Its free-tier token cap rejects the ~12k-token retrieval prompt, so generation
  is single-model by design; failover is disabled in evaluation so a rate limit
  fails loudly rather than silently blending two models.
- Transient errors (503/429) are retried with backoff; a schema or key error is
  not — it is a bug, not a blip.

---

## 8. Evaluation methodology

The evaluation set is the submission's evidence, so it is guarded against a
circular result:

- **Frozen before any retrieval code existed** (git-verifiable), so questions
  could not be shaped to fit the retriever. Questions may be added later, never
  rewritten — least of all one the system fails.
- **Authored by reading the specifications, not the chunks.** Questions written
  from chunk text inherit its vocabulary and inflate retrieval toward 1.0. Gold
  clause ids were read from the documents, never taken from system output.
- **50 questions**: 36 answerable, 14 out-of-scope.
- **The groundedness judge is a different model than the generator**, because a
  model grading its own output is biased toward it.

Results (`gemini-3.7-flash`, judged by `gpt-oss-120b`), committed per-question in
[`eval/results/gemini.sanitized.json`](eval/results/gemini.sanitized.json):

| Metric | Result |
|--------|--------|
| Groundedness — judged answers supported by their cited clauses | **33 / 33 (1.00)** |
| Out-of-scope refusal — out-of-scope questions correctly declined | **14 / 14 (1.00)** |
| Full-gold retrieval recall | **30 / 36 (0.83)** |
| False-refusal rate — answerable questions wrongly declined | **3 / 36 (0.08)** |

Every answer produced was grounded in the clause it cited, and every out-of-scope
question was refused. Gate 3 never had to fire at runtime — no generated answer
reached the user with a quote that failed the verbatim check. The three false
refusals are the safe error direction: the system withholds rather than risk an
unsupported answer.

---

## 9. Trade-offs and known limitations

Stated plainly, because knowing a design's limits is part of the design:

- **Gate-1 thresholds are calibrated on the same 50-question set they are
  reported on.** With n=50 a held-out split was not statistically meaningful, so
  transparency was chosen over a false hold-out. The generation and groundedness
  metrics are *not* fit to the threshold; the refusal calibration is in-sample.
- **Small evaluation set.** 33/33 and 14/14 are perfect but over small n; the
  claim is "grounded on every answer in a frozen, spec-authored sample," not a
  generalisation guarantee.
- **Gate 3 verifies that a quote is real, not that it entails the answer.** At
  runtime, "grounded" means the cited quote exists verbatim in the cited clause
  — a strong, cheap necessary condition. True entailment is checked *offline* by
  the independent groundedness judge, not in the live path.
- **Recall is 0.83; cross-specification is the weak spot** (3/5). A missed clause
  becomes a refusal — the safe direction — but it caps usefulness.
- **Gate 2 is the one gate inside the model** (its self-reported `sufficient` /
  `answerable_from_standards` booleans), backstopped by the deterministic Gate 3.

---

## 10. Tech stack

Python 3.11 · ChromaDB (vector store) · rank-bm25 · `sentence-transformers`
(BGE-small embeddings) · Google Gemini (generation) · Groq (groundedness judge)
· FastAPI (service) · Streamlit (client) · Pydantic (the model contract) · `uv`
(packaging). No orchestration framework — the pipeline is explicit by choice, so
its behaviour is fully owned in ~1,300 lines of tested code.
