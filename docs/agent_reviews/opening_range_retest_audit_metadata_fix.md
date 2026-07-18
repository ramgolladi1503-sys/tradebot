# Opening Range Retest Audit Metadata Fix

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Align ORB replay shard metadata audit
- scope: Correct metadata parity between ORB replay summary and source-manifest artifacts.
- requested_paths: `research/opening_range_retest/replay_engine.py`, `tests/test_opening_range_retest_causal_replay.py`, `tests/test_opening_range_retest_merge_certification.py`, `docs/agent_reviews/opening_range_retest_audit_metadata_fix.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy logic, broker paths, risk paths, feed paths, execution paths, credentials, corpus roots
- expected_tests: focused ORB replay tests, independent five-session smoke audits, py_compile, ruff, diff check, evidence gate, CE gates, full suite
- acceptance_proof: `ORB_AUDIT_METADATA_FIX_READY`

## Scope Guard

This change is research replay evidence plumbing only. It does not change `strategies/`, runtime strategy thresholds, profiles, broker APIs, risk gates, feed gates, execution behavior, or authoritative corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_ARTIFACT
- candidate_id: opening_range_retest_audit_metadata_fix
- decision: ORB_AUDIT_METADATA_FIX_READY
- reason: Corrects source-manifest shard metadata so independent audit can verify summary/source parity for unsharded, child-shard, and merged replay artifacts.
- timestamp: 2026-07-18T22:30:00+05:30
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/opening_range_retest_audit_metadata_fix.md

## Grill Me Review

The defect on merge commit `92874c00` was real: a five-session authoritative smoke generated replay artifacts, but `scripts/audit_opening_range_retest_causal_replay.py` rejected them with `summary_manifest_shard_metadata_mismatch`. The root cause was missing non-merged fields in `source_manifest["shard_metadata"]`: `merged_from_shards` and `merged_shard_indexes`. The audit script was correct to reject inconsistent evidence.

## Hermes Review

The intended shard-metadata contract is explicit:

- Unsharded replay: `shard_count=1`, `shard_index=0`, `is_sharded_run=false`, `merged_from_shards=false`, `merged_shard_indexes=[0]`, and before/after selected counts equal.
- Individual shard replay: requested `shard_count`, requested `shard_index`, `is_sharded_run=true`, `merged_from_shards=false`, `merged_shard_indexes=[shard_index]`, before count equals full source universe, after count equals current shard record count.
- Merged replay: original `shard_count`, `shard_index=null`, `is_sharded_run=true`, `merged_from_shards=true`, `merged_shard_indexes` covers every index exactly once, before/after counts equal reconstructed universe.

Summary uses `selected_file_count_*`; source manifest uses `selected_record_count_*`. The auditor normalizes those names before equality comparison.

## GSD Review

Changed files are narrow and evidence-only. `research/opening_range_retest/replay_engine.py` now writes the missing non-merged metadata fields in the source manifest. Tests cover positive metadata parity and negative audit rejection when shard metadata is tampered.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true where applicable
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
- append=false for generated evidence contracts unless explicitly writing replay artifacts

## Acceptance Proof

To be filled by the final validation pass before PR:

- focused tests repeated three times
- related ORB suites
- smoke A audit
- smoke B audit
- py_compile
- ruff
- git diff --check
- agent-review evidence validation
- CE gates
- full suite

## Runtime Proof Required After Merge

This PR does not verify ORB post-merge semantics. After human merge, a fresh `origin/main` SHA must be recorded and one authoritative 12-shard ORB post-merge replay must independently audit READY before `ORB_POSTMERGE_VERIFIED` can be claimed.

## What This PR Does Not Prove

- It does not prove the merged-main ORB candidate hash.
- It does not prove production readiness, live readiness, paper readiness, fills, slippage, latency, option execution, or profitability.
- It does not change strategy behavior.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
