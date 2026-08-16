# Reciprocal Rank Fusion orders results; it never gates refusals

Hybrid retrieval fuses BM25 and dense rankings with Reciprocal Rank Fusion,
`RRF(d) = Σ 1/(k + rank_i(d))`. **RRF consumes ranks, not similarities.** Its top-ranked
document scores `1/(k+1)` whether that document is a perfect match or the least-irrelevant
chunk in a corpus containing nothing relevant at all. Thresholding a fused score therefore
cannot distinguish a good answer from the best of a bad lot — the refusal gate would never
fire. Gate 1 thresholds the **raw** dense-cosine and BM25 scores instead, calibrated
empirically against the frozen eval set.

An earlier draft of the design specified exactly this mistake. It was caught in review
rather than in testing, which is why it is recorded here.

## Consequences

**`Hit` deliberately carries three scores** — `cosine`, `bm25` and `rrf`. The redundancy is
the point: raw scores gate, the fused score orders. Anything that discards the raw scores
after fusion breaks refusal.

**Either raw signal alone passes the gate.** BM25 carries exact identifiers (`T310`,
`SRB1`) that dense similarity blurs; dense carries paraphrases that keyword search misses.
Requiring both would refuse legitimate questions of each kind.

**Thresholds must be fitted, not chosen.** `bge` cosine similarities are compressed —
loosely related text still scores around 0.7 — so the usable band is narrow. Both
thresholds stay `null` and the gate stays inactive until calibration runs.

**A regression test pins this.** `test_rrf_top_score_is_rank_based_not_relevance_based`
asserts that a relevant and an irrelevant single-item ranking receive identical RRF scores.
If someone "simplifies" the gate to read the fused score, that test explains why not.
