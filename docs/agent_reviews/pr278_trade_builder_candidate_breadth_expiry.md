# PR 278 Agent Review Evidence — Trade Builder Candidate Breadth Expiry Fix

mode: TEST
candidate_id: PR278_TRADE_BUILDER_CANDIDATE_BREADTH_EXPIRY
candidate_status: documentation_evidence
rank: 0
rank_reason: process_gate_evidence_only
liquidity_score: 0
risk_score: 0
execution_score: 0
data_quality_penalty: 0
decision: FIX_EXPIRED_TEST_FIXTURE_DATES
reason: Candidate breadth tests used March and April 2026 option expiries, which became expired and caused valid production expiry filtering to remove all fixture contracts.
timestamp: 2026-05-26T08:35:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md

## Agent Work Contract

- PR scope: update `tests/test_trade_builder_candidate_breadth.py` fixture expiries so the tests remain valid after March and April 2026.
- Changed files: `tests/test_trade_builder_candidate_breadth.py` and this evidence document.
- No production trade-builder logic is changed.
- No broker, execution, strategy, WebSocket, or dashboard behavior is touched.

## Scope Guard

- In scope: replace expired test fixture dates with stable future test fixture dates.
- Out of scope: weakening option expiry validation, changing contract resolution, modifying trade scoring, or altering candidate ranking.
- Files changed list: `tests/test_trade_builder_candidate_breadth.py`, `docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md`.
- Files not touched list: `strategies/trade_builder.py`, `core/kite_client.py`, execution paths, broker adapters, dashboard paths.

## Grill Me Review

- Question: What assumption silently killed the tests?
- Answer: The tests assumed March and April 2026 expiries would remain future contracts. On 2026-05-26 they are expired.
- Question: What behavior is claimed but not proven?
- Answer: This PR only proves candidate breadth tests use non-expired fixture contracts. It does not prove live option-chain availability.
- Question: What would fail even if tests pass?
- Answer: A production option chain with expired contracts should still be rejected. This PR intentionally does not change production expiry filtering.

## Hermes Review

- Scope status: pass.
- Boundary violations: none.
- Files not to touch check: production trade builder and broker paths remain untouched.
- Verdict: test fixture maintenance only.

## GSD Review

- purpose: keep candidate breadth tests deterministic as calendar time moves forward.
- scope: replace hardcoded expired fixture expiries with stable future fixture constants.
- files_changed: test fixture and agent review evidence.
- tests_or_reason_not_required: run the focused candidate breadth test file and full pytest suite.
- evidence: local run showed 3 failures caused by `CHAIN_EMPTY` after expired fixture contracts were filtered out.
- risks: using unrealistic far-future dates is acceptable for a pure unit fixture because the test validates ordering, deduplication, and setup-family metadata, not exchange calendar validity.
- next_pr: none for this fix.

## QA / Safety Review

- Safety boundary: no order action, no broker call, no live execution behavior.
- The fix preserves production fail-closed behavior for expired contracts.
- The fix changes only synthetic test data.
- The fix is expected to unblock the 3 local failures in `tests/test_trade_builder_candidate_breadth.py`.

## Acceptance Proof

Planned validation commands:

```bash
python -m pytest -q tests/test_trade_builder_candidate_breadth.py
python -m pytest -q tests
./run_live.sh --validate-only
```

Expected proof:

- `test_duplicate_candidate_rows_are_suppressed` returns one ranked candidate.
- `test_strike_ladder_generation_is_deterministic` returns offsets `[0, -1, 1, -2, 2]`.
- `test_force_family_emits_canonical_setup_family_metadata` returns `mean-reversion` setup-family metadata.

## Runtime Proof Required After Merge

- Pull latest `main` after merge.
- Re-run `python -m pytest -q tests/test_trade_builder_candidate_breadth.py` locally.
- Re-run `python -m pytest -q tests` locally.
- Run `./run_live.sh --validate-only` before live observation.

## What This PR Does Not Prove

- It does not prove live market feed health.
- It does not prove broker connectivity.
- It does not prove option-chain contract availability for a real trading day.
- It does not prove strategy profitability.
- It does not change candidate ranking logic.

## Human Approval

- Human approval required before merge.
- Reviewer should verify the patch is limited to replacing expired synthetic fixture dates and adding evidence.

## High-Risk Path Review

N/A
