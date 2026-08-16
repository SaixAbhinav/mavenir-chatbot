# Pin the whole corpus to one 3GPP Release

3GPP specifications evolve independently, so taking the newest published version of each of
the seven specs would mix releases — a Release 18 TS 38.331 beside a Release 16 TS 28.552.
A cross-specification answer would then assemble clauses describing different versions of
the system: every citation individually valid, the composite describing no real system. We
pin all seven specifications to **the newest release for which all seven have a published
version**, derived by inspecting the archive rather than chosen from knowledge.

This is a correctness decision, not tidiness. No gate can catch a release mismatch — both
the citation and the supporting quote check out — so it has to be prevented at ingest.

## Consequences

**Citations are meaningless without their version.** Clause numbers move between releases,
so every citation renders as `TS 38.331 v17.5.0 §5.3.5.3`, never as a bare clause id.

**The corpus is not current.** Pinning to the newest *common* release means individual
specs may lag their own latest version. This is stated in the README rather than hidden.

**Changing the release invalidates the eval set**, because gold clause ids are read from
the pinned versions. Treat a release bump as re-authoring evaluation questions.

Multi-release support with release-aware retrieval is recorded as future work — it lifts
this constraint properly rather than by ignoring it.
