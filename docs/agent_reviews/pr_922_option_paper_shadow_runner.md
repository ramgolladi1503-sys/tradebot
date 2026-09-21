# Agent Review Evidence — PR 922: Option Paper Shadow Runner & Late Day Refresh

## Agent Work Contract

### Scope

Add option shadow paper runner, late-day option refresh helper, and authoritative contract-level cost model evaluation for DAY_TO_NIGHT_MOMENTUM_V2.

### Files Changed

- `core/candidate_audits/cost_model.py`
- `core/paper_shadow/run_day_to_night_option_shadow.py`
- `core/paper_shadow/run_day_to_night_shadow.py`
- `core/upstox_capture/late_day_option_refresh.py`
- `docs/research/candidates/DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION/FROZEN_SPEC.json`
- `docs/research/candidates/DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION/FROZEN_SPEC.sha256`
- `runtime/paper_shadow/DAY_TO_NIGHT_MOMENTUM_V1/verification_session_20260917.json`
- `runtime/paper_shadow/DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION/option_verification_session_20260917.json`
- `runtime/paper_shadow/DAY_TO_NIGHT_MOMENTUM_V2_OPTION/option_verification_session_20260917.json`
- `scripts/research/audit_option_depth_feasibility.py`
- `scripts/research/reprice_contract_level_all_epochs.py`
- `scripts/upstox_daily_live_capture_and_stitch.py`
- `tests/research/test_indian_derivatives_cost_model.py`
- `tests/test_candidate_costs.py`
- `tests/test_day_to_night_option_shadow.py`
- `tests/test_no_hardcoded_paths_repo_wide.py`
- `tests/test_upstox_daily_live_capture.py`

### Files Not To Touch

- `config/`
- `credentials.py`
- broker adapters (`core/broker*`)
- live execution paths (`core/execution*`, `core/order*`, `core/risk*`)
- kill switches and risk gates
- unrelated strategy logic

### Expected Proof

- Strict read-only contracts (`read_only=true`, `is_order_action=false`, `broker_api_called=false`).
- Deterministic test coverage for statutory schedule, late-day strike refresh, and shadow simulator.
- Zero mock-away of trading safety boundaries.

### Evidence Contract Fields

mode: PAPER
candidate_id: DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION
decision: VERIFY_OPTION_PAPER_SHADOW
reason: Authoritative contract-level option shadow runner and statutory cost model verification.
timestamp: 2026-09-21T18:30:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_922_option_paper_shadow_runner.md

## Scope Guard

### In Scope

- Read-only option shadow verification runner.
- Statutory transaction cost schedule aware of October 2024 and April 2026 STT changes.
- Late-day strike subscription refresh logic for market capture.
- Frozen spec hashes for candidate `DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION`.

### Out of Scope

- Order placement, order cancellation, order modification.
- Live trading execution logic.
- Broker API calls.
- Credential management or secrets.

### Boundary Verification

- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`

## Grill Me Review

### Challenge

Are the statutory fee schedules accurately partitioned between pre-Oct 2024, post-Oct 2024, and post-April 2026? Does late-day refresh mutate active live orders or execute broker mutations?

### Weaknesses Found & Remediated

- Historical tests previously expected pre-2024 statutory schedules when calling `calculate_cost` with `trade_date=None`. Explicit historical test fixture dates were parameterized in `tests/test_candidate_costs.py` while preserving 2026 rate validation in `tests/research/test_indian_derivatives_cost_model.py`.
- Trailing whitespace and newline formatting across PR diffs were cleaned to meet repo git-diff checks.

### Verdict

PASS

## Hermes Review

### Architecture & Contract Alignment

- Option paper shadow runner produces read-only JSON execution records with complete ledger accounting.
- Late-day option refresh only computes candidate strike keys for WebSocket feed subscription, completely segregated from order routing or broker execution engines.
- Cost model preserves immutable `CostBreakdown` structures with verified turnover and stamp duty formulas.

### Safety Invariants

- Zero live execution wiring.
- Read-only simulation boundary strictly enforced.

### Verdict

PASS

## GSD Review

### Delivery & Scoped Execution

- Scoped implementation delivering candidate verification for `DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION`.
- Comprehensive unit test suites proving:
  1. Indian derivatives cost model schedules (`tests/research/test_indian_derivatives_cost_model.py`)
  2. Candidate cost calculations under historical regimes (`tests/test_candidate_costs.py`)
  3. Option paper shadow simulation accuracy (`tests/test_day_to_night_option_shadow.py`)
  4. Late-day strike refresh logic (`tests/test_upstox_daily_live_capture.py`)
  5. Repository path compliance (`tests/test_no_hardcoded_paths_repo_wide.py`)

### Verdict

PASS

## QA / Safety Review

### Verification Gates Passed

- `tests/test_candidate_costs.py`: PASS (3 tests)
- `tests/test_no_hardcoded_paths_repo_wide.py`: PASS
- `tests/test_day_to_night_option_shadow.py`: PASS
- `tests/research/test_indian_derivatives_cost_model.py`: PASS
- `tests/test_upstox_daily_live_capture.py`: PASS

All tests pass deterministically offline with no external network access or broker dependencies.

### Verdict

PASS

## Acceptance Proof

```bash
/opt/anaconda3/bin/python3 -m pytest -q \
  tests/test_candidate_costs.py \
  tests/test_no_hardcoded_paths_repo_wide.py \
  tests/test_day_to_night_option_shadow.py \
  tests/research/test_indian_derivatives_cost_model.py \
  tests/test_upstox_daily_live_capture.py
```

Expected and observed output: 13 passed in feature branch local environment.

## Runtime Proof Required After Merge

- Verification session files under `runtime/paper_shadow/DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION/` remain readable and immutable.
- Any future paper shadow runner invocations remain isolated offline and produce audited output logs.

## What This PR Does Not Prove

- Does not authorize live order placement.
- Does not authorize automated live execution of option strategies.
- Does not modify live broker gateways.

## Human Approval

Approved for merge under sequential integration sequence: PR #922 -> PR #924 -> PR #925 -> PR #926.

## High-Risk Path Review

N/A — No high risk paths (`config/`, `core/auth.py`, `core/kite_depth_ws.py`, `core/orchestrator.py`, `core/execution*`, `core/risk*`, `strategies/`) were modified in this PR.
