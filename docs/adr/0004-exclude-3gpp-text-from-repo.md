# Exclude © 3GPP text from the repository rather than commit it

3GPP's terms state that copyright vests jointly with the Organizational Partners and that no
part may be reproduced except by written permission, with that restriction extending to all
media. 3GPP specifications are free to download; that is not the same as free to
redistribute. A committed vector index holds the full body text of all seven specifications,
so committing it and publishing the repository would be wholesale redistribution of
copyrighted standards text.

**Decision: the repository is public, but no copyrighted 3GPP text is committed to it.** The
raw downloads (`data/raw/`), the normalised conversions (`data/normalised/`), and the built
index (`data/index/`) are all git-ignored. A reviewer regenerates the index locally with the
ingest pipeline; the hosted demo builds it at deploy time. `NOTICE.md` records attribution
and provenance.

## Considered options

**Private repository with a committed index**, shared directly with the assessor as a
submission rather than a publication. Rejected: a public repository is worth more as a
portfolio and submission artifact, and the copyright concern is fully addressed by excluding
the text rather than by hiding the whole repository.

**Public repository with embeddings and clause ids but no body text.** Rejected outright: it
breaks verbatim quote anchoring and source display, which are the anti-hallucination
guarantees the project is built on.

## Consequences

**The reviewer must build the index once** (`uv run python -m noc_copilot.ingest`), which
needs a LibreOffice install and a few minutes of ingest. This is the cost of keeping the
repository publishable, and it is documented in the README.

**The hosted demo shows only retrieved clauses** for a given question — single cited
quotations rather than bulk republication — with attribution in the footer.

The audience matters here: Mavenir operates inside the 3GPP/ETSI ecosystem, where IPR
discipline is professional hygiene rather than pedantry.
