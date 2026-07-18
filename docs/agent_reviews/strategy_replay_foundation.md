# Strategy Replay Foundation

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Add reusable strategy replay foundation
- scope: Add research-only replay artifact, evidence-envelope, and shard-merge helpers for downstream strategy certification lanes.
- requested_paths: `research/strategy_replay/__init__.py`, `research/strategy_replay/common.py`, `research/strategy_replay/git_state.py`, `research/strategy_replay/merge.py`, `tests/test_strategy_replay_common.py`, `tests/test_strategy_replay_merge.py`, `docs/agent_reviews/strategy_replay_foundation.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy logic, broker paths, risk paths, feed paths, execution paths, credentials, corpus roots
- expected_tests: focused strategy replay foundation tests, py_compile, ruff, diff check, agent-review evidence validation
- acceptance_proof: `STRATEGY_REPLAY_FOUNDATION_READY`

## Scope Guard

This change is research replay infrastructure only. It does not wire any strategy to runtime execution, change strategy thresholds, import broker clients, change risk gates, change feed gates, or create any LIVE/PAPER behavior.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_ARTIFACT
- candidate_id: strategy_replay_foundation
- decision: STRATEGY_REPLAY_FOUNDATION_READY
- reason: Adds reusable fail-closed replay artifact helpers for downstream strategy replay certification with deterministic ledger hashing and strict shard metadata validation.
- timestamp: 2026-07-18T23:20:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/strategy_replay_foundation.md

## Grill Me Review

The initial foundation checkpoint was directionally useful but under-specified for safety evidence. It accepted artifact envelopes without `read_only`, `append`, or `allowed_for_live_execution`, wrote ledger artifacts as bare JSON, allowed a merged summary to default to `READY` unless explicit negative counts appeared, and did not prove order-independent ledger hashing. Those are unsafe defaults for replay certification.

## Hermes Review

The reusable contract now treats every artifact, including ledgers, as evidence with explicit safety flags. Shard merges must prove shard verdict readiness before combining data, then prove summary/source-manifest shard metadata parity, deterministic source partition assignment, non-zero oracle checks, future-mutation checks, and source-immutability checks before returning a certifying merged bundle.

## GSD Review

Changed files remain narrow:

- `research/strategy_replay/common.py`: evidence envelope validation now requires `read_only=true`, `append=false`, and `allowed_for_live_execution=false`.
- `research/strategy_replay/common.py`: candidate hashes are order-independent and duplicate ledger identities are rejected.
- `research/strategy_replay/merge.py`: artifact writer envelopes ledgers; artifact loader rejects legacy bare ledgers; payloads cannot override protected evidence fields; merge rejects missing/non-READY shard verdicts, zero checked controls, metadata mismatches, and source partition mismatches.
- `tests/test_strategy_replay_common.py`: unsafe envelope values, order-independent ledger hashes, and duplicate ledger identities are rejected.
- `tests/test_strategy_replay_merge.py`: ledger-envelope, protected field override, non-ready shard, zero-control, metadata mismatch, partition mismatch, and shard-order independence failures are covered.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true where applicable
- append=false for evidence contracts
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Validation completed before PR:

- `pytest -q tests/test_strategy_replay_common.py tests/test_strategy_replay_merge.py --maxfail=1`: `14 passed in 1.07s`
- `ruff check research/strategy_replay tests/test_strategy_replay_common.py tests/test_strategy_replay_merge.py`: passed
- `python3 -m py_compile research/strategy_replay/*.py tests/test_strategy_replay_common.py tests/test_strategy_replay_merge.py`: passed
- `git diff --check`: passed
- `PYTHONPATH=. python3 scripts/run_unified_ce_gates.py --repo . --config .gsd-forensics.yaml --changed-paths-file /tmp/foundation_pr670_changed_paths.txt --out /tmp/foundation_pr670_ce_report.md`: passed with `total_blocks=0`

## Runtime Proof Required After Merge

This PR does not certify any strategy replay by itself. Downstream strategy lanes must generate their own artifacts, candidate hashes, source manifests, ledger hashes, and independent audits before claiming replay readiness.

## What This PR Does Not Prove

- It does not wire Trend, VWAP, ORB, or any other strategy to the new foundation.
- It does not prove strategy profitability, paper readiness, live readiness, broker behavior, fills, slippage, or option execution.
- It does not prove ORB post-merge verification.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
