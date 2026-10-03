# Hermes Addendum — Issue 7 canonical corpus target-date recheck

**source_agent:** hermes
**action:** MAP_WORKFLOW, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Verify whether the registered NIFTY futures corpus contains the Sep. 30, 2026 T-1 bar
**scope:** Read-only inspection of two existing aligned Parquet payloads and the V3 registry/coverage metadata. No data mount writes, source promotion, runtime changes, or prerequisite staging.

## Finding

The V3 source registry labels the registered NIFTY spot/futures aligned source as covering 2024–2026. The associated V3 data-quality matrix is more precise: 185,681 rows in 496 sessions, ending `2026-07-28 15:29:00+05:30`, with one invalid OHLC row and partial volume/OI semantics. The repo payload hash matches the V3 registry hash. A separate repaired V2 copy has one fewer row. Exact target-date queries of both Parquet files found no `2026-09-30` session rows. The Sep. 30 stitched live capture was separately scanned and contains no FUT-labelled symbols.

## Contract

1. Treat year-level registry labels as discovery metadata; target-date presence must be checked in the actual payload.
2. Do not synthesize, stage, or promote Sep. 30 futures values from later/earlier dates, spot/index data, token ordering, or the patched capture.
3. Preserve the existing fail-closed Issue 7 loader and `UNKNOWN_T1_SOURCE_AND_MANIFEST_AUTHORITY_NOT_ESTABLISHED` disposition.
4. Record hashes, row/session bounds, exact-target row counts, and the source-provenance limits. Do not call processed dataset metadata raw source authority.

## Acceptance proof

PyArrow queries of both files report 0 rows for `session_date == 2026-09-30`; both maximum session dates are `2026-07-28`. The repository payload SHA matches the registered V3 SHA-256. Existing JSON artifact/graph and source manifest validation passes after documentation updates.

## Limits and authority

This is a bounded read-only check of the registered aligned files, the repaired V2 copy, the V3 registry and quality metadata, and the already scanned same-day capture. It does not prove that no unregistered source exists anywhere in external storage. It does establish that the named canonical payloads cannot supply this target-date T-1 row. No source values are authorized. `read_only=true`, `append=false`, no broker/order/live action.

## Agent Work Contract

Campaign issue contract; see `issues_7_11_campaign_review.md` for the PR-level Hermes/GSD scope and actions.

## Scope Guard

Issue-level design boundary and restrictions are defined above; the consolidated review records the full campaign boundary.

## Grill Me Review

Campaign risk critique and unresolved proof limits are recorded in `issues_7_11_campaign_review.md`.

## Hermes Review

This file is the issue-specific Hermes contract. The consolidated review records the cross-issue architecture review.

## GSD Review

Execution evidence and test limits are recorded in `issues_7_11_campaign_review.md`; this contract alone is not implementation proof.

## QA / Safety Review

Safety boundary and verification limits are recorded in `issues_7_11_campaign_review.md`.

## High-Risk Path Review

See `issues_7_11_campaign_review.md` for the cross-cutting review of feed and orchestrator high-risk paths. This issue contract does not authorize runtime or broker actions.

## Acceptance Proof

Issue-specific acceptance criteria are defined above. Cross-issue executed proof and its limitations are recorded in `issues_7_11_campaign_review.md`.

## Runtime Proof Required After Merge

Runtime proof requirements are recorded in `issues_7_11_campaign_review.md`; offline contract text does not establish runtime parity.

## What This PR Does Not Prove

See the consolidated review for campaign-level limitations. This issue contract does not independently claim live verification.

## Human Approval

This design contract does not represent human approval. The PR remains subject to human review as described in `issues_7_11_campaign_review.md`.
