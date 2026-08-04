# Upstox 2026-08-04 Corpus Audit — Agent Review Evidence

## Agent Work Contract

Build a provider-neutral, read-only audit and PR #786 rehearsal tool for the locally retained Upstox V3 corpus reported for 2026-08-04.

The tool must verify existing artifacts without modifying them and must stamp all generated rehearsal evidence as:

```text
source=upstox_replay
offline_replay=true
live_source=false
not_certification_evidence=true
```

It must never claim Kite live certification, option-corpus coverage, profitability, or structural edge.

## Scope Guard

Allowed production paths:

- `core/upstox_corpus_audit.py`
- `scripts/audit_upstox_20260804_corpus.py`

Allowed supporting paths:

- focused tests and workflow;
- this review document;
- offline closure documentation after tests pass.

Explicitly forbidden:

- feed startup;
- broker, order, fill, or execution construction;
- strategy or threshold changes;
- modification of the local sealed Upstox corpus;
- modification of the sealed Kite evidence root;
- merging Upstox artifacts into Kite certification.

## Grill Me Review

Questions that must remain answerable from code and tests:

- Does the audit open SQLite in read-only mode?
- Does it use `partitioning=None` for Parquet reads?
- Does it verify zstd decompression instead of trusting file existence?
- Does it independently recompute manifest file hashes?
- Does deterministic replay compare ordered row-stream hashes, not just totals?
- Does row reconciliation avoid incorrectly adding tick and depth counts?
- Does a duplicate interval identity fail closed?
- Does the rehearsal produce one authority snapshot and one primary evaluation per interval?
- Are every rehearsal row and export explicitly `live_source=false`?
- Does canonical sealing create `artifact_manifest.json`, `SHA256SUMS`, and `SEALED`?
- Does post-seal mutation fail verification?

## Hermes Review

Evidence chain:

```text
immutable local capture
→ zstd decompression and SHA audit
→ normalized Parquet schema/count audit
→ manifest-reference hash verification
→ two read-only SQLite replay semantic hashes
→ explicit row-count reconciliation
→ stable completed-interval identities
→ offline authority and MEG ledger rehearsal
→ canonical seal
```

The rehearsal ledger is intentionally not live MEG evidence. It validates serialization, append-only durability, stable interval identity, duplicate suppression, and sealing behavior only.

## GSD Review

Goal: remove preventable evidence surprises before the next governed Kite session.

Signals:

- source paths are snapshotted before and after;
- the audit root must be separate from all source roots;
- missing local data produces `NOT_RUN` or failed gates, never fabricated success;
- unexplained normalized-versus-tick rows fail reconciliation;
- offline outputs cannot satisfy a live-source gate;
- the next Kite session remains mandatory.

Decision boundary:

```text
Offline Upstox rehearsal ≠ Kite live certification.
```

## QA / Safety Review

Required safety properties:

- `read_only=true`;
- `broker_api_called=false`;
- `broker_write_authority=false`;
- `order_authority=false`;
- `allowed_for_live_execution=false`;
- `allowed_for_paper_execution=false`;
- no provider token is treated as interchangeable with a Kite token;
- no source artifact is rewritten;
- no raw zstd, Parquet, or SQLite data is committed.

Tests cover decompression, Parquet reads, manifest tampering, ordered replay parity, tick/depth overlap accounting, duplicate interval rejection, offline evidence labels, canonical sealing, and post-seal mutation detection.

## Acceptance Proof

Acceptance requires all of the following on one commit:

- changed modules compile;
- focused audit and PR #786 contract tests pass;
- the same suites pass in reverse order;
- protected runtime drift is false;
- diff check passes;
- Agent Review Evidence Gate passes;
- no change-related repository regression is found.

The real million-row corpus cannot be independently executed by GitHub CI while it remains only on the user's Mac. Therefore fixture proof and corpus proof are reported separately.

## Runtime Proof Required After Merge

Do not merge this audit tool merely because fixture tests pass.

Before the next Kite session, the local corpus runner should produce:

- raw zstd audit;
- normalized Parquet audit;
- manifest lineage verification;
- two deterministic replay database hashes;
- zero unexplained replay rows;
- unique bar interval identities;
- a sealed PR #786 offline rehearsal;
- a truthful readiness verdict.

The next market-hours Kite run must still independently prove live subscriptions, live authority snapshots, live MEG export, persistence reconciliation, graceful shutdown, canonical sealing, PR #782 pass, and PR #783 assembly.

## What This PR Does Not Prove

This PR does not prove:

- that the reported local commit `ce1d9737...` exists remotely;
- that the local million-row corpus matches Antigravity's summary;
- that the Upstox corpus contains option-chain observations;
- that MEG produced a structural edge or market signal;
- that Kite live certification has passed;
- profitability, execution quality, fill quality, or autonomous readiness.

## Human Approval

Human approval is required before merge and before using any local audit output as authoritative evidence.

Reviewers must confirm:

- the source corpus was not modified;
- actual local paths and hashes are present in the final report;
- all required gates ran rather than being silently skipped;
- offline labels are preserved;
- the PR remains draft until corpus-level results are reviewed.
