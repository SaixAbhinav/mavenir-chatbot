# Design: 3GPP NOC Chatbot

This document explains what was built and why. For setup and how to run it, see
[`README.md`](README.md).

## 1. The problem

A network-operations engineer needs precise answers about 5G standards, and needs
to cite the source. A normal chatbot fails here in one specific way: it makes
things up. It answers with confidence even when it does not know. For a standard,
a wrong answer is worse than no answer, because the reader cannot tell it is
wrong.

So the goal is simple. The system should only answer from the official documents,
show the exact clause it used, and say "I don't know" when the documents do not
cover the question. Saying "I don't know" is treated as a correct answer, not a
failure.

## 2. How it works, end to end

The flow is written out step by step. There is no LangChain, LlamaIndex, or agent
framework. Every step is plain code, so it is easy to read and easy to debug.

```
question
  -> Retrieve      find the most relevant clauses (two search methods, combined)
  -> Gate 1        if nothing relevant was found, refuse now (no AI call yet)
  -> Generate      ask Gemini for an answer in a fixed JSON format
  -> Gate 2        the model says whether the clauses actually cover the question
  -> Gate 3        check, in code, that each quote really appears in the clause
  -> return the answer with citations, or a refusal with a reason
```

A FastAPI service does all the work. A small Streamlit page shows the result. The
page has no logic of its own, so the system can be tested without a browser.

The code is split into small modules:

| Module | What it does |
|--------|--------------|
| `acquire.py`, `versions.py` | download the specs from 3GPP and lock their versions |
| `clauses.py` | read a `.docx` file and split it into individual clauses |
| `chunking.py` | turn each clause into one searchable piece of text |
| `store.py` | create the embeddings and save the search database |
| `retrieve.py` | run the search, combine the two methods, and shape the results |
| `guards.py` | the three safety checks (the gates) |
| `generate.py` | call the model and handle retries |
| `pipeline.py` | connect search, gates, and generation into one flow |
| `api.py` | the web service |

## 3. The documents

The system uses seven 3GPP specifications. All are locked to Release 17, so
answers that combine several specs describe the same version of the system. The
specs are: TS 38.300 (overview), 38.321 (MAC), 38.322 (RLC), 38.323 (PDCP),
38.331 (RRC), 28.545 (fault supervision), and 28.552 (performance measurements).
Together they become 2,085 searchable pieces.

Key choices:

- Split the documents by clause, not by fixed length. A clause is the natural unit
  in a spec, and it is what you cite. Each piece maps to exactly one clause, so it
  can always be cited back to the reader.
- Leave out the ASN.1 code sections. They are huge, nearly identical to each
  other, and would flood the search with noise. The change-history sections are
  also removed, because they are just edit logs. The code even checks that these
  never slip in by accident.
- Keep the list of what to include or exclude in a config file, not buried in the
  parser. This makes the corpus easy to adjust.
- Do not store the search database in the repo. It contains copyrighted 3GPP text,
  so it is rebuilt locally instead. Answers only ever show short, quoted snippets.

## 4. Turning clauses into searchable text

Each searchable piece is the clause text with a short header on top. The header is
the full path to the clause, including the number and title at each level, for
example
`TS 38.331 v17.17.0 § 5 Procedures > 5.3 Connection control > 5.3.13 RRC connection resume > 5.3.13.6 ...`.
This header is searched too, so a question can match on context even when the
clause body is very short.

Two details matter:

- Never cut a clause in the middle of a sentence. A mid-sentence cut would break
  the quote check in Gate 3, which is the heart of the whole system. If a
  paragraph is too long, it is kept whole instead of being split badly.
- Some clauses reuse the same number. When that happens, they are numbered in
  order so each piece stays unique. Because the versions are locked, this ordering
  is always the same.

## 5. Search

The search uses two methods and combines them.

- Meaning-based search (embeddings) catches paraphrases and questions worded
  differently from the spec.
- Keyword search (BM25) catches exact terms an engineer types, like a timer name
  or a counter such as `periodicBSR-Timer`.
- Neither method alone is enough, so both run and their results are merged.

More choices:

- The corpus is small (about 2,000 pieces), so the meaning-based search compares
  against everything directly. This is fast and finds the true best matches, with
  no accuracy lost to shortcuts.
- The method that merges the two result lists (RRF) is used only to decide the
  order. It is never used to decide whether something is relevant, because it
  loses that information. The relevance check uses the original raw scores
  instead.
- No single spec is allowed to dominate the results. One spec (TS 28.552) has
  hundreds of near-identical clauses, so a limit per spec keeps the other specs in
  view.
- If a procedure is split across neighbouring clauses, the neighbours are added
  back in afterward, so the model sees the full picture. These added clauses are
  marked and kept out of the relevance check. The final context is about 11
  clauses: 8 top-ranked, plus up to 4 siblings, so at most 12.

## 6. Stopping made-up answers

This is the core of the design. For every way the model could make something up,
there is one specific check that stops it. The three checks (the gates) run
outside the model, so the model cannot argue its way past them.

| How a made-up answer could happen | What stops it |
|-----------------------------------|---------------|
| The model answers from its own training instead of the documents | The prompt gives it only the retrieved clauses and tells it to ignore outside knowledge. It also runs at temperature 0, so output is stable. |
| The model answers when nothing relevant was found | Gate 1 refuses based on the raw search scores, before the model is even called. This is fast and does not depend on the model. |
| The model stretches weak clauses into a confident answer | Gate 2 makes the model state whether the clauses really cover the question, and flag questions that are about a live network rather than the standards. |
| The model invents a clause number or reworders a quote | Gate 3 checks, in code, that every quote appears word-for-word in the clause it points to. If it does not, the answer is thrown away, not shown. |
| The quote is real but does not actually support the answer | During evaluation, a different model checks whether the answer follows from the quote, so the check is independent of the model being graded. |

When the system refuses, it says why, using one of four reasons: nothing relevant
was found, the clauses do not have the detail, the question is about a live
network, or the answer could not be verified. These mean different things to an
engineer, so they are kept separate.

The model must reply in a fixed JSON format (answer, whether it is sufficient,
whether it is answerable from the standards, and the citations). This is what
makes Gates 2 and 3 simple, mechanical checks instead of guesswork.

If a quote fails the word-for-word check, the model gets exactly one more try,
with a reminder to copy the quote exactly. After that it refuses. The other
refusals are not retried, because a re-ask would not change them.

## 7. Generation

- Temperature 0 everywhere, so the same question gives the same answer.
- Gemini (`gemini-3.7-flash`) writes the answers. It was picked by testing which
  model copies quotes most faithfully. An earlier model merged two bullet points
  into one quote and failed Gate 3.
- Groq (`gpt-oss-120b`) is wired in as a backup writer, but its free-tier limit
  is too small for the long retrieval prompt, so in practice every answer comes
  from Gemini. Groq's real job is the grader during evaluation, where the backup
  is turned off so a failure is loud instead of silently switching models.
- Temporary errors (like a busy server) are retried with a short wait. A real
  error, like a bad key, is not retried, because it is a bug and will not fix
  itself.

## 8. How it was evaluated

The test set is the proof, so it is protected from cheating.

- The questions were frozen before the search code was written, which git history
  shows. This means the questions could not be tuned to match the search. New
  questions can be added later, but existing ones are never rewritten, especially
  not one the system got wrong.
- The questions were written by reading the specs, not by reading the search
  pieces. Writing from the pieces would copy their exact words and make the search
  look better than it is. The correct clause for each question was read from the
  document by hand.
- There are 50 questions: 36 that should be answered, 14 that should be refused.
- The grader is a different model from the writer, because a model grading its own
  work tends to favour it.

Results (`gemini-3.7-flash`, graded by `gpt-oss-120b`), saved question by question
in [`eval/results/gemini.sanitized.json`](eval/results/gemini.sanitized.json):

| Metric | Result |
|--------|--------|
| Answers that were actually supported by their cited clause | 33 / 33 (1.00) |
| Out-of-scope questions correctly refused | 14 / 14 (1.00) |
| Questions where the correct clause was retrieved | 30 / 36 (0.83) |
| Answerable questions wrongly refused | 3 / 36 (0.08) |

Every answer the system gave was backed by its cited clause, and every
out-of-scope question was refused. Gate 3 never had to reject anything at run
time, meaning no bad quote ever reached it. The three wrong refusals fail in the
safe direction: the system holds back instead of guessing.

## 9. Trade-offs and limits

Stated plainly:

- The Gate 1 thresholds were tuned on the same 50 questions they are reported on.
  With only 50 questions, a separate test split would not have been meaningful, so
  honesty was chosen over a fake one. The answer-quality numbers are not affected
  by this tuning; only the refusal thresholds are.
- The test set is small. 33/33 and 14/14 look perfect, but on a small set that is
  not a guarantee it will always hold. The claim is only about this frozen set.
- Gate 3 confirms a quote is real, not that it proves the answer. At run time,
  "grounded" means the quote exists in the cited clause, which is a strong and
  cheap check. Whether the quote truly proves the answer is checked separately by
  the grader, not live.
- Retrieval finds the right clause 83% of the time. Questions spanning two specs
  are a weak spot (3 of 5 retrieved), which is expected since the answer lives in
  two documents at once. A miss becomes a refusal, which is safe, but it limits
  how often the system can help.
- Gate 2 is the only check that runs inside the model. It is backed up by Gate 3,
  which runs outside it.

## 10. Tech stack

Python 3.11, ChromaDB (search database), rank-bm25 (keyword search),
sentence-transformers (embeddings), Google Gemini (writing answers), Groq
(grading), FastAPI (web service), Streamlit (interface), Pydantic (the response
format), and uv (packaging). No orchestration framework. The flow is written by
hand, so all of its behaviour lives in about 1,300 lines of tested code.
