# GSD Plan — Issue 7 Prior-Day Capture Recheck

**source_agent:** gsd
**action:** PLAN_PR, UPDATE_DOCS
**title:** Record whether the September 30 capture can authorize October 1 T-1 futures data
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**Hermes contracts:** `docs/agent_reviews/issues_7_11_hermes_t1_capture_recheck.md`; `docs/agent_reviews/issues_7_11_hermes_issue7_canonical_corpus_recheck.md`

## Allowed files

- `docs/agent_reviews/issues_7_11_hermes_t1_capture_recheck.md`
- `artifacts/issues_7_11/GSD_T1_CAPTURE_RECHECK_PLAN.md`
- `artifacts/issues_7_11/CAPTURE_CORPUS_RECHECK_20261003.md`
- `artifacts/issues_7_11/FINAL_VERDICT.json`
- `artifacts/issues_7_11/defect_graph.json` and `.md`
- `artifacts/issues_7_11/attack_ledger.jsonl` and `repair_ledger.jsonl`
- `artifacts/issues_7_11/WORKTREE_SOURCE_MANIFEST_20261003.json`

No runtime source, configuration, strategy, feed/risk gate, or broker/order file is in scope.

## Execution

1. Read the September 30 stitched capture and matching summary without modifying either.
2. Hash both source files.
3. Inspect Parquet row count and schema.
4. Scan the `symbol` column across all rows for futures-labelled instruments.
5. Record limits: no original event IDs, payload hashes, or separate receive timestamp.
6. Preserve the Issue 7 UNKNOWN disposition and clarify replay-only admissibility.

## Validation

- Recompute both source SHA-256 hashes.
- Confirm the recorded row count/schema and futures-symbol scan result.
- Parse `artifacts/issues_7_11/defect_graph.json` and `artifacts/issues_7_11/FINAL_VERDICT.json`.
- Run `git diff --check`.
- No pytest run is required for this documentation-only evidence update.

## Acceptance

The new evidence is accurately bounded to the inspected files; missing source authority is not promoted to PASS; no runtime behavior, trading authority, or strategy semantics change.


## Canonical corpus payload recheck — 2026-10-03

Hermes addendum: `docs/agent_reviews/issues_7_11_hermes_issue7_canonical_corpus_recheck.md`. The V3 registry's `TRADEBOT_LEGACY_BROKER_V1` source points to the repo Parquet with SHA-256 `2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9`; it has 185,681 rows, session range 2024-07-26 through 2026-07-28, and zero rows for 2026-09-30. The repaired V2 copy at `/Volumes/TradeBotData/NIFTY_SPOT_FUTURES_ALIGNED_V2_repaired.parquet` has SHA-256 `0108b00bcf62f2b42621fb3b3919b69d3faf6bc362776232c1faff8131107f9a`, 185,680 rows, the same session range, and zero target-date rows. V3 quality metadata reports one invalid OHLC row and volume/OI semantics limited. This proves only absence from these named payloads; provenance remains partial and external unregistered sources are not exhaustively excluded. Issue 7 remains UNKNOWN and fail-closed.
