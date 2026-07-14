# PR #99 — Live Observation Runtime Safety Flags

## Agent Work Contract

### Scope

Make live observation capable of disabling runtime order reconciliation explicitly and safely. The immediate production bug is that `main.py` defaults missing `ORDER_RECON_ENABLED` to `True`, which can start reconciliation during validation even when the operator passes `ORDER_RECON_ENABLED=false` but `config.py` does not define the key.

### Files changed

- `main.py`
- `tests/test_main_startup_audit.py`
- `docs/agent_reviews/PR99_LIVE_OBSERVATION_RUNTIME_SAFETY_FLAGS.md`

### Hard boundaries

- No broker calls.
- No live order submission.
- No submit/modify/cancel/exit behavior.
- No dashboard changes.
- No strategy/scoring/ranking changes.
- No feed subscription changes.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

- Missing `ORDER_RECON_ENABLED` must default to disabled.
- `ORDER_RECON_ENABLED=false` must disable reconciliation.
- `ORDER_RECON_ENABLED=true` may enable reconciliation explicitly.
- Existing broker truth reconciliation remains opt-in via `BROKER_TRUTH_RECONCILE_ENABLED`.

## Grill Me Review

### Challenge

A live observation run is not safe if hidden reconciliation daemons start by default. The previous code used `getattr(cfg, "ORDER_RECON_ENABLED", True)`, which is unsafe when the config key is absent.

### Findings

- Good: missing config now fails safe to disabled.
- Good: env override is explicit and deterministic.
- Good: tests prove default disabled and explicit opt-in.
- Constraint: this PR does not fix option feed subscription; it only makes the next live observation safer.

### Result

Approved with no-broker/no-runtime-expansion constraint.

## Hermes Review

### Scope verification

- No broker adapter imports added.
- No live execution enablement.
- No dashboard files touched.
- No strategy/scoring/ranking files touched.
- No feed code touched.
- No order state machine mutation.
- No ledger mutation.

### Safety verification

- Reconciliation is now opt-in instead of implicitly enabled.
- Env override controls the flag deterministically.
- Tests cover missing config key and explicit enablement.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add `_truthy_env(...)` helper.
2. Add `_order_reconciliation_enabled(...)` helper with default false.
3. Replace unsafe default in `main.py`.
4. Add tests for missing config key, env false, env true, and daemon start behavior.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_main_startup_audit.py
```

### Result

Approved.

## Scope Guard

### In scope

- Runtime safety flag behavior.
- Startup tests.
- 3-agent evidence.

### Out of scope

- Broker API calls.
- Live execution.
- Runtime observation run.
- Option feed subscription repair.
- Dashboard.
- Strategy/scoring/ranking changes.
- Fill/slippage changes.
- PR #100+ work.

### Result

PASS.

## Approval + Evidence

PR #99 is approved for PR creation once targeted tests pass.

Evidence summary for PR body/comment:

- Agent Work Contract: PASS
- Grill Me: PASS with no-broker/no-runtime-expansion constraint
- Hermes: PASS
- GSD: PASS
- Scope Guard: PASS


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A
