## Agent Work Contract

- **source_agent**: Codex
- **action**: UPDATE_DOCS, FIX_TEST_FAILURE
- **title**: Replay-context evidence and safe NIFTY ingestion scaffolding
- **scope**: Keep the branch evidence-only and replay-only while satisfying CI evidence gates.
- **requested_paths**: `core/replay_candidate_handoff_entrypoint.py`, `tests/vertical_slice/test_nifty_real_replay_vertical_slice.py`, `docs/agent_reviews/ram_next_isolated_work_pr648.md`
- **allowed_paths**: `core/*`, `tests/*`, `docs/agent_reviews/*`
- **forbidden_paths**: `main.py`, `runtime/live*`, `broker*`, `order*`, `risk*`
- **expected_tests**: `tests/test_candidate_journal.py`, `tests/test_edge_79a_s_runtime_candidate_handoff_evidence.py`, `tests/test_replay_candidate_handoff_entrypoint.py`, `tests/test_nifty_futures_ingestion_validation.py`, `tests/vertical_slice/test_nifty_real_replay_vertical_slice.py`
- **acceptance_proof**: CI evidence gates pass and the branch stays replay-only.

## Scope Guard

This PR stays inside replay evidence, recorder metadata, isolated replay handoff, and public-safe NIFTY ingestion validation. It does not touch live execution, broker APIs, order placement, or risk gates.

## Grill Me Review

The weak point is evidence drift: replay proof tooling can still look stronger than it is if non-action fields are not explicit or if tests only prove shape. The branch must keep `is_order_action=false`, `broker_api_called=false`, `live_order_action=false`, and `broker_order_action=false` explicit in the replay handoff evidence.

## Hermes Review

The design remains aligned with the existing replay-only architecture. The new evidence file and explicit non-action metadata do not widen execution scope; they only make the safety contract visible to CI and reviewers.

## GSD Review

The branch adds isolated replay handoff and NIFTY ingestion validation scaffolding. The remaining work is evidence hygiene: make the replay handoff manifestly read-only and keep the vertical-slice replay test from reading as a confidence-only assertion.

## QA / Safety Review

- mode: AGENT_REVIEW
- item_id: PR-648
- candidate_id: N/A
- decision: BASELINE
- result: reviewed
- reason: replay evidence and safe ingestion scaffolding only
- timestamp: 2026-07-12T17:00:00Z
- flag_value: false
- call_value: false
- source: static_review
- read_only=true where applicable
- is_order_action=false
- broker_api_called=false
- live_order_action=false
- broker_order_action=false
- allowed_for_live_execution=false unless explicitly scoped and human-approved
- append=false where evidence/contracts are read-only

## Acceptance Proof

- Focused replay/journal/ingestion tests pass locally.
- The replay handoff emits explicit isolated-output and non-action markers.
- The branch remains free of live order or broker mutations.

## Runtime Proof Required After Merge

None for this PR. The branch is evidence/scaffold work only.

## What This PR Does Not Prove

It does not prove live trading readiness, profitable edge, or WFA certification. It does not prove that the existing real replay artifacts naturally regenerate a candidate without richer runtime context.

## Human Approval

Approved for replay-only evidence hardening. No live execution changes authorized.
