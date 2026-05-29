# LIVE-TRUTH-31 — Pre-Market Live Readiness Gate

## Agent Work Contract

Issue: #442 — LIVE-TRUTH-31 — Pre-Market Live Readiness Gate.

This PR adds a read-only pre-market readiness command for LIVE startup validation. The work is intentionally limited to a gate/evaluator, a CLI wrapper, deterministic tests, and this review evidence.

## Scope Guard

In scope:
- Add `core/pre_live_readiness_gate.py` as the pure readiness evaluator.
- Add `scripts/pre_live_readiness_gate.py` as the command wrapper.
- Add deterministic tests for fallback, token universe, auth/latch, market-closed pending proof, and exact JSON blockers.

Out of scope:
- No strategy behavior.
- No ranking/scoring weight changes.
- No dashboard/UI changes.
- No execution adapter changes.
- No live order behavior.

## Grill Me Review

Hard questions answered:

1. Can this place or route an order?
   - No. The payload marks the gate as read-only and non-action, and the implementation does not call execution adapters.

2. Can this falsely claim live tick proof when the market is closed?
   - No. Market closed returns `MARKET_CLOSED_PENDING_TICK_PROOF` when there are no hard blockers.

3. Does LIVE fail closed on unsafe inputs?
   - Yes. LIVE fails on fallback execution flags, zero option universe, invalid auth state, active auth latch, feed breaker trip, or feed lock failure.

## Hermes Review

The command emits machine-readable JSON with:
- `outcome`
- `ready`
- `blockers`
- `warnings`
- `checks`
- `exit_code`

Hard failures exit nonzero. Market-closed pending tick proof exits zero with an explicit warning and `ready=false`.

## GSD Review

This is not an evidence-only PR. It adds runnable readiness code and deterministic test coverage. The implementation is small on purpose: one core evaluator, one CLI wrapper, and one focused test module.

## QA / Safety Review

Covered by deterministic tests:
- fallback execution enabled in LIVE fails.
- zero option universe fails.
- invalid auth plus auth latch fails.
- valid safe inputs pass during market-open conditions.
- market-closed mode does not falsely pass live tick proof.
- JSON contains the exact blocker list.

Safety properties:
- No dashboard/UI path touched.
- No strategy/ranking path touched.
- No execution path touched.
- Auth readiness uses local cached state and credential presence, not a forced external profile probe.

## Acceptance Proof

Expected command:

```bash
PYTHONPATH=. python scripts/pre_live_readiness_gate.py --mode LIVE --json
```

Focused tests:

```bash
PYTHONPATH=. python -m pytest -q tests/test_pre_live_readiness_gate.py
python -m py_compile scripts/pre_live_readiness_gate.py
```

Acceptance mapping:
- LIVE fallback enabled -> `FAIL` with `fallback_execution_enabled_live`.
- Zero option universe -> `FAIL` with `token_universe_zero`.
- Invalid auth/latch -> `FAIL` with `auth_invalid` / `auth_required_latch_active`.
- Safe config -> `PASS` or `MARKET_CLOSED_PENDING_TICK_PROOF` depending on market state.
- JSON includes exact blocker list.

## Runtime Proof Required After Merge

Before the next live session, run:

```bash
PYTHONPATH=. python scripts/pre_live_readiness_gate.py --mode LIVE --json
```

Required runtime evidence:
- If market is closed, outcome must be `MARKET_CLOSED_PENDING_TICK_PROOF` or hard `FAIL`, never a false tick-proof pass.
- If market is open and unsafe, outcome must be `FAIL` with exact blockers.
- If market is open and safe, outcome may be `PASS`.

## What This PR Does Not Prove

This PR does not prove profitability, ranking edge, strategy quality, feed recovery after startup, or live executable candidate quality. It only proves that a pre-market LIVE readiness gate exists and fails closed on the scoped unsafe startup states.

## Human Approval

Human approval is required before treating this gate as part of the operational LIVE startup procedure. The PR must remain unmerged until CI is green and the reviewer accepts the read-only scope boundary.
