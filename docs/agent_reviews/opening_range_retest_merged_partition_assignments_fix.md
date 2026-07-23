# Opening Range Retest Merged Partition Assignments Fix

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Preserve ORB merged source-manifest partition assignments
- scope: Fix ORB replay merge metadata so merged artifacts retain one deterministic partition assignment per merged source record.
- requested_paths: `research/opening_range_retest/replay_engine.py`, `tests/test_opening_range_retest_merge_certification.py`, `docs/agent_reviews/opening_range_retest_merged_partition_assignments_fix.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy logic, broker paths, risk paths, feed paths, execution paths, credentials, corpus roots
- expected_tests: focused ORB merge certification tests, py_compile, ruff, diff check, agent-review evidence validation
- acceptance_proof: `ORB_MERGED_PARTITION_ASSIGNMENTS_FIX_READY`

## Scope Guard

This change is research replay evidence plumbing only. It does not change `strategies/`, runtime strategy thresholds, profiles, broker APIs, risk gates, feed gates, execution behavior, or authoritative corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_ARTIFACT
- candidate_id: opening_range_retest_merged_partition_assignments_fix
- decision: ORB_MERGED_PARTITION_ASSIGNMENTS_FIX_READY
- reason: Post-merge 12-shard ORB replay generated READY shards and a READY merged summary, but independent audit rejected the merged artifact because the merge path dropped `partition_assignments`.
- timestamp: 2026-07-19T00:40:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/opening_range_retest_merged_partition_assignments_fix.md

## Grill Me Review

The failure is real and blocks `ORB_POSTMERGE_VERIFIED`: `/tmp/orb-postmerge-8646a238-12shard-1784396700/merged` had `selected_file_count=1512` and `records=1512`, but `partition_assignments=0`; `scripts/audit_opening_range_retest_causal_replay.py` correctly failed with `partition_assignment_count_mismatch`.

## Hermes Review

The merged source manifest must preserve the same deterministic partition proof as child shards. For every merged record, the manifest now records symbol, session date, logical path, selected source SHA, canonical session key, and recomputed `sha256(canonical_session_key) mod shard_count` shard index.

## GSD Review

Changed files are narrow:

- `research/opening_range_retest/replay_engine.py`: merged manifests rebuild `partition_assignments` from `combined_records`.
- `tests/test_opening_range_retest_merge_certification.py`: positive merge certification asserts merged assignment identity matches merged records and shard indexes cover the expected child shards.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Validation completed before PR:

- `pytest -q tests/test_opening_range_retest_merge_certification.py --maxfail=1`: `24 passed in 8.13s`
- `ruff check research/opening_range_retest/replay_engine.py tests/test_opening_range_retest_merge_certification.py`: passed
- `python3 -m py_compile research/opening_range_retest/replay_engine.py tests/test_opening_range_retest_merge_certification.py`: passed
- `git diff --check`: passed

## Runtime Proof Required After Merge

After human merge, a fresh exact `origin/main` SHA must run the authoritative 12-shard ORB replay and independent audit again before `ORB_POSTMERGE_VERIFIED` can be claimed.

## What This PR Does Not Prove

- It does not prove ORB post-merge verification yet because the fix is not on `origin/main`.
- It does not prove production readiness, live readiness, paper readiness, broker behavior, fills, slippage, option execution, or profitability.
- It does not change strategy behavior.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
