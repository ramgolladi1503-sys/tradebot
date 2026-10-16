# PR #986 — Accept and Verify Heritage Manifest SHA256 in MROS Live Session Runner

## Evidence Contract Fields

- mode: LIVE_OBSERVATION_RUNNER_ARGUMENT_PARITY
- candidate_id: pr986-mros-heritage-manifest-sha256-arg
- decision: REVIEW_ONLY
- reason: Accept and verify `--heritage-manifest-sha256` in `scripts/run_market_event_graph_live_session_v1.py` to match orchestrator dispatch contract and enforce cryptographic manifest integrity.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #986
- Branch: `fix/mros-heritage-manifest-sha256-arg`
- Scope: Implementation and verification of `--heritage-manifest-sha256` argument in MROS runner:
  - Add `--heritage-manifest-sha256` argument to `argparse` parser in `scripts/run_market_event_graph_live_session_v1.py`.
  - Validate candidate manifest against provided sha256 digest fail-closed (`BLOCKED_BY_HERITAGE_MANIFEST_SHA256_MISMATCH`).
  - Unit tests in `tests/test_run_market_event_graph_live_session_v1.py` proving argument acceptance, validation pass, and mismatch rejection.
- Requested paths:
  - `scripts/run_market_event_graph_live_session_v1.py`
  - `tests/test_run_market_event_graph_live_session_v1.py`
  - `docs/agent_reviews/pr986_mros_heritage_manifest_sha256_arg.md`
  - `governance/evidence/CLAIM_REGISTRY.json`
  - `governance/evidence/work_items/LIVE-OBS-MROS-HERITAGE-SHA-20261016.json`
- Allowed paths: the requested paths above only.
- Forbidden paths/behaviors: broker order placement or modification, secrets, live trading enablement, bypassing risk gates or feed freshness checks, credentials, .env files.
- Expected tests: 11/11 passing tests in `tests/test_run_market_event_graph_live_session_v1.py`.
- Acceptance proof: passing test suite, clean git diff --check, evidence gate verification.

## Scope Guard

Verdict: PASS

- All modifications strictly adhere to CLI argument parity and cryptographic verification of the heritage manifest.
- No live broker orders are placed, cancelled, or altered (`is_order_action: false`, `broker_api_called: false`).
- Zero changes to broker order routing, risk throttles, or account credentials.

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`scripts/run_market_event_graph_live_session_v1.py` is the live session orchestrator entrypoint. Changes are strictly confined to:
1. Adding `--heritage-manifest-sha256` to argparse options.
2. If `--heritage-manifest-sha256` is provided, computing the actual manifest SHA256 and terminating with `BLOCKED_BY_HERITAGE_MANIFEST_SHA256_MISMATCH` if digests differ.
3. If matches, assigning `heritage_manifest_sha256 = computed_sha` and proceeding normally.
All order-execution and risk-gating paths remain un-gated and strictly read-only.

## Grill Me Review

Verdict: PASS

Adversarial critique resolved with empirical constraints:
- Invariant I-1: CLI argument parity ensures `core/governed_morning_orchestrator.py` dispatches successfully without `unrecognized arguments: --heritage-manifest-sha256`.
- Invariant I-2: Cryptographic validation is fail-closed; any mismatch immediately halts execution before session initialization.
- Invariant I-3: Optionality is preserved; when no SHA256 is passed, existing manifest ingestion behavior remains intact.
- Invariant I-4: Zero order actions, zero credential leaks, strictly read-only telemetry.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Architectural invariants formally defined:
- Verifies input integrity of T-1 heritage manifest cryptographically before reading graph nodes.
- Preserves orchestrator -> runner command contract.

## GSD Review

Verdict: PASS

All scoped work items implemented cleanly with proof-driven tests. 11 tests execute cleanly in under 15 seconds.

## QA / Safety Review

Verdict: PASS

- 11 passed tests in `tests/test_run_market_event_graph_live_session_v1.py`.
- Dedicated verification tests:
  - `test_session_orchestrator_accepts_and_verifies_heritage_manifest_sha256`: PASS
  - `test_session_orchestrator_rejects_heritage_manifest_sha256_mismatch`: PASS
- Non-negotiables verified:
  - `read_only = True`
  - `is_order_action = False`
  - `broker_api_called = False`
  - `allowed_for_live_execution = False`

## Acceptance Proof

```text
pytest tests/test_run_market_event_graph_live_session_v1.py -q
11 passed, 2 warnings in 13.92s
```

## Runtime Proof Required After Merge

During Monday morning governed launcher start:
1. Verify `step_start_market_event_graph_observer()` dispatches `scripts/run_market_event_graph_live_session_v1.py` with `--heritage-manifest-sha256` and starts successfully.
2. Confirm PID file is recorded and state advances beyond BLOCKED.

## What This PR Does Not Prove

1. It does not certify algorithmic trading profitability.
2. It does not authorize live automated order placement with capital risk.
3. It does not replace human operator monitoring during market open/close.

## Human Approval

Approved by USER in task prompt: "option A".
