# ORB Context Cycle Cutoff Main V2

- mode: RUNTIME_REPAIR
- candidate_id: orb-context-cycle-cutoff-main-v2
- decision: MERGE_AFTER_REQUIRED_CHECKS_PASS
- reason: Replace an undefined ORB timestamp argument with the already-frozen per-cycle cutoff and prove the production caller forwards that exact value.
- timestamp: 2026-07-29T10:20:00Z
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/orb_context_cycle_cutoff_main_v2.md

## Agent Work Contract

Repair only the ORB context timestamp propagation defect in `core/market_data.py`, add focused regression coverage, and avoid all strategy, risk, execution, broker, configuration, and live-permission changes.

## Scope Guard

Changed scope is limited to:

- `core/market_data.py`;
- `tests/core/test_orb_context_cycle_cutoff.py`;
- this review-evidence document.

The branch replaces the undefined `now` argument with the already-frozen per-cycle `cycle_cutoff`. No strategy threshold, signal equation, risk gate, order path, broker call, feed subscription, dashboard behaviour, or runtime configuration is changed.

## Grill Me Review

Challenge: could changing the timestamp alter ORB eligibility?

Answer: the previous code passed an undefined variable and the exception could be swallowed by the surrounding feed path. The repair supplies the exact cycle timestamp already captured by `now_ist()`. It does not introduce a new clock read or change ORB calculations.

Challenge: could the test pass while production still uses another timestamp?

Answer: the regression test intercepts `_orb_state_from_candles()` through `fetch_live_market_data()` and asserts equality with the frozen `cycle_cutoff`. It also rejects a one-second-shifted value and verifies the resulting ORB state reaches the market-data row.

## Hermes Review

The change is deterministic and minimal. It removes unused symbols only where required for the scoped lint gate. No fallback behaviour or silent substitution was added.

## GSD Review

The implementation directly fixes the named runtime defect rather than adding architecture. The focused test exercises the production caller boundary and fails if `now`, a second clock read, or another timestamp is supplied.

## QA / Safety Review

- Broker APIs called: `NO`.
- Orders placed, modified, or cancelled: `NO`.
- Strategy formulas or thresholds changed: `NO`.
- Risk or kill-switch behaviour changed: `NO`.
- Feed freshness rules changed: `NO`.
- Live configuration changed: `NO`.
- Research data or runtime artifacts committed: `NO`.

## Acceptance Proof

Previously recorded focused verification:

- `pytest -q tests/core/test_orb_context_cycle_cutoff.py`: `1 passed`;
- `pytest -q tests/core/test_canonical_strategy_input_truth.py`: `21 passed`;
- `python3 -m py_compile core/market_data.py tests/core/test_orb_context_cycle_cutoff.py`: passed;
- `ruff check core/market_data.py tests/core/test_orb_context_cycle_cutoff.py`: passed;
- `git diff --check`: passed.

Repository GitHub Actions must rerun on the updated branch before merge.

Validation refresh: this evidence-only update intentionally retriggers all required checks against the current protected-branch merge base after GitHub reported the named `repo-forensics-pr-gate` context as expected despite the prior visible green run.

## Runtime Proof Required After Merge

During the next market-data smoke run, confirm that ORB context generation completes without the prior swallowed `NameError`, and that the logged/snapshotted ORB cutoff equals the cycle cutoff used for the same market-data iteration.

## What This PR Does Not Prove

This PR does not prove ORB profitability, structural edge, option execution quality, feed availability, paper readiness, or live trading readiness. It only repairs timestamp propagation into the existing ORB context calculation.

## Human Approval

The user explicitly requested that valuable infrastructure and runtime fixes be repaired, validated, and merged. Merge remains conditional on current required checks passing and GitHub branch protection permitting the merge.
