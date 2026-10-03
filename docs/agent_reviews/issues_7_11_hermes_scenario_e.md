# Hermes Contract — Scenario E: Restart, stale required contract, advisory

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Verify stale required spot remains blocked after durable restart and advisory reads the scoped ledger
**scope:** deterministic offline composition plus additive closed-authority metadata on every CAS result, readiness receipt, and artifact
**requested_paths:** `core/read_only_consumer_cycle.py`, `tests/test_issues_7_11_scenario_b_restart.py`, `tests/test_read_only_consumer_cycle.py`, and Issues 7–11 evidence artifacts
**allowed_paths:** `core/read_only_consumer_cycle.py` (explicit non-authorizing metadata on all CAS outputs only), both listed tests, this contract, the GSD plan, and named campaign evidence artifacts
**forbidden_paths:** all other production source/config, strategy semantics, feed/risk/broker/order behavior, credentials, token universe, runtime processes, PR #936
**expected_tests:** reopened completed-bar store plus stale required NIFTY spot blocks the actual CAS evaluator; the actual advisory projection reads the explicit valid-empty candidate-decision ledger; every CAS result state (PENDING or PASS), readiness receipt, and CAS artifact carries the complete closed-authority tuple, including duplicate/completion-failure exits
**acceptance_proof:** use the existing Scenario B restart fixture and actual `produce_and_store_runtime_snapshots`, `_evaluate_cas`, and `_build_advisory_latest_payload`; assert durable memory is restored, stale NIFTY blocks CAS artifact creation, advisory source is the supplied ledger with zero rows, and exact authority fields are preserved on the CAS gate, all PENDING/PASS results, all writable readiness receipts, and advisory CAS artifact; a write-failure branch returns closed authority without retrying a failed receipt write
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `paper_authorized=false`, `live_authorized=false`, `allowed_for_live_execution=false`

## Contract boundaries

Add only non-authorizing metadata to CAS result states, readiness receipts, and advisory artifacts on both success and failure paths. Preserve the current decision, reason, cutoff, risk-halt handling, and file-writing method; apply the same metadata contract to success and failure outputs. This additive schema makes closed authority explicit; it does not create a new execution gate or alter a strategy decision.

The completed-bar fixture is explicitly `deterministic_test` data and establishes only the store/restart code path. It is not a market-source or CAS primitive authority. Verified same-session primitives come from the existing hash-bound synthetic fixture; Scenario E deliberately makes the current required NIFTY spot stale, so the bridge must reject those primitives for this cycle. The advisory reader is a read-only projection of the explicitly selected, valid-empty candidate-decision ledger. It must not fabricate rows or turn historical bars into candidate authority.

## Fail-closed invariants

1. A restored bar history cannot override stale/missing/mismatched current required spot health.
2. A blocked CAS evaluation creates no artifact.
3. The advisory row count reflects the supplied source; empty means zero rows, not an inferred candidate.
4. Advisory rows remain non-executable and do not imply paper/live permission.
5. No runtime service, broker, order, feed, strategy decision, or configuration behavior is changed. Production edits are additive, non-authorizing metadata on CAS outputs.

## Acceptance and limits

The targeted test must pass and directly attack stale required spot after restart. The test is offline/synthetic; it cannot establish captured source lineage, actual service restart, generic candidate-level dependency isolation, captured/live parity, or campaign completion.
