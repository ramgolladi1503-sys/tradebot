# v4.10.1 Option Replay Blocker Invalidation

## Agent Work Contract
- `source_agent`: `Codex`
- `action`: `REPAIR`
- `scope`: `Invalidate the v4.10.1 blocker-label split as a signal-execution proof and preserve the fail-closed research boundary.`
- `requested_paths`:
  - `docs/agent_reviews/option_e2e_v4_10_1_option_replay_blocker_invalidation.md`
  - `research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json`
  - `research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json.sha256`
- `allowed_paths`:
  - `docs/agent_reviews/*`
  - `research/option_e2e_recertification_v4/v4_10_2_supersession/*`
- `forbidden_paths`:
  - `broker*`
  - `runtime/live*`
  - `credentials*`
  - `risk*`
  - `dashboard*`
  - `production*`
- `expected_tests`:
  - `PYTHONPATH=. pytest -q tests/research/option_e2e/test_signal_ledgers_v4_10_2.py`
- `acceptance_proof`:
  - `The v4.10.2 package returns zero signal rows and keeps invalidated historical evidence out of current signal evidence.`

## Scope Guard
- `research_only=true`
- `allowed_for_live_execution=false`
- `broker_api_called=false`
- `is_order_action=false`
- No broker, live order, live feed, credentials, risk gate, dashboard, or production-threshold changes.

## Grill Me Review
- The earlier v4.10.1 blocker split was still only a blocker-context distinction.
- It did not prove a VWAP signal row.
- It did not import or execute a frozen VWAP contract.

## Hermes Review
- Keep the evidence boundary narrow.
- Separate legacy replay audits from invalidated historical records.
- Do not treat blocker records as signal rows.

## GSD Review
- Preserve the invalidation record.
- Keep the package fail-closed.
- Do not broaden scope to live or broker paths.

## QA / Safety Review
- The evidence remains read-only.
- The output remains non-executable.
- No fake signals are emitted.

## Acceptance Proof
- Focused tests passed for the blocker-context package.
- Current output contains zero signal rows.
- Invalidated historical evidence is excluded from active signal evidence.

## Runtime Proof Required After Merge
- Re-run the checked v4.10.2 test file in CI.
- Verify no live, broker, or order paths were touched.
- Verify the invalidated historical record remains excluded from current evidence.

## What This PR Does Not Prove
- No VWAP signal was executed.
- No signal ledger was certified.
- No production readiness claim is made.
- No profitability, holdout, or WFA result is claimed.

## Human Approval
- Required before any move toward live execution or broker integration.
- Not granted by this repository change.
