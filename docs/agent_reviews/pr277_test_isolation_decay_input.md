# PR 277 Agent Review Evidence — Test Isolation and Decay Input Handling

mode: TEST
candidate_id: PR277_TEST_ISOLATION_DECAY_INPUT
candidate_status: documentation_evidence
rank: 0
rank_reason: process_gate_evidence_only
liquidity_score: 0
risk_score: 0
execution_score: 0
data_quality_penalty: 0
decision: FIX_TEST_ISOLATION_AND_INPUT_PRECEDENCE
reason: Test runtime state and replay input precedence needed deterministic boundaries before live-regression tests could be trusted.
timestamp: 2026-05-26T08:15:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/pr277_test_isolation_decay_input.md

## Agent Work Contract

- PR scope: fix deterministic test execution and explicit decay dataset input handling.
- Changed files: `tests/conftest.py`, `ml/decay_dataset.py`, and this evidence document.
- No runtime trading behavior is intentionally changed.
- No broker order path, execution router, strategy generator, WebSocket runtime, or dashboard behavior is touched.

## Scope Guard

- The pytest fixture only affects test execution.
- The decay dataset loader change only affects input precedence: an explicitly supplied JSONL file remains authoritative, including when empty.
- The change does not weaken live-mode assertions.
- The change does not introduce new production fallbacks.
- The change does not add any broker calls.

## Grill Me Review

- Question: Could the pytest fixture hide a real bug by clearing `TRADING_MODE` or `DRY_RUN`?
- Answer: No for tests that explicitly monkeypatch `cfg.EXECUTION_MODE`; it prevents shell state from overriding the test contract. Tests that need env-mode behavior must set the env explicitly inside the test.
- Question: Could the decay loader ignore valid DB data?
- Answer: Only when a caller explicitly supplies an existing JSONL file. That is the correct precedence because explicit replay input must not be mixed with default DB state.
- Question: Could this patch weaken safety checks?
- Answer: No. It strengthens deterministic test isolation so safety tests execute under their declared mode.

## Hermes Review

- Communication risk: The original PR description said CI failures were likely runtime contamination. The CI confirmed additional process requirements: CE classification and mandatory agent review evidence.
- Evidence path added here so reviewers can see what changed, what was intentionally excluded, and what still needs runtime proof after merge.
- No user-facing product behavior is claimed as fixed by this PR.

## GSD Review

- Problem: Local and CI test behavior can be polluted by shell env, stale runtime roots, lock files, auth cooldown state, or unrelated DB rows.
- Fix: isolate pytest runtime roots and make explicit decay JSONL input authoritative.
- Result expected: targeted tests should no longer fail because of stale local state or unrelated persisted artifacts.
- Non-goal: solving any remaining genuine production logic failure discovered after test isolation.

## QA / Safety Review

- Safety boundary: no broker calls, no order placement, no live execution behavior.
- Test fixture clears leaked `TRADING_MODE` and `DRY_RUN` before each test.
- Test fixture assigns isolated data/log/lock/db/report roots per test.
- Test fixture resets historical auth cooldown state per test.
- Decay dataset now avoids mixing explicit JSONL replay input with unrelated SQLite decision events.

## Acceptance Proof

Planned validation commands:

```bash
python -m pytest -q tests/test_auth_health.py tests/test_cross_asset_stale.py tests/test_decay_dataset.py tests/test_decision_dag.py tests/test_gatekeeper_cross_asset.py tests/test_invalid_ltp.py tests/test_kite_client_auth_guard.py tests/test_option_chain_error_logging.py tests/test_orchestrator_pro_shadow.py tests/test_strategy_gatekeeper_mode_thresholds.py tests/test_time_sanity_staleness.py tests/test_trade_builder_soft_vetoes.py
python -m pytest -q tests
```

Expected proof:

- Agent Review Evidence Gate passes because this file contains the mandatory review sections.
- Code Excellence Gate passes after the fixture no longer uses silent `except/pass` and has explicit evidence/assertion signal.
- Decay empty-input test writes an empty schema parquet instead of loading unrelated DB rows.

## Runtime Proof Required After Merge

- Re-run the previously failing local command in a clean shell and in a shell with stale `TRADING_MODE` / `DRY_RUN` to prove test isolation is effective.
- Confirm CI `tests` and `ci` workflows are green on the PR head.
- Confirm no runtime directories are created under the repository during pytest.

## What This PR Does Not Prove

- It does not prove all live trading behavior is correct.
- It does not prove strategy profitability.
- It does not prove broker integration health.
- It does not prove WebSocket feed continuity.
- It does not prove remaining failures are impossible; it only removes known contamination paths.

## Human Approval

- Human approval required before merge.
- Reviewer should verify this PR remains limited to test isolation, decay input precedence, and evidence documentation.