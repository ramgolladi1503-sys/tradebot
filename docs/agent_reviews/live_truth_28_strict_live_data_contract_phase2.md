# Agent Review Evidence — LIVE-TRUTH-28 Strict LIVE Data Contract for Phase2

## Agent Work Contract

### Goal

In LIVE/REAL execution mode, Phase2 must reject/downgrade candidates with absent or fallback-driven market data instead of silently filling defaults that could become executable.

### Files changed

- `core/_engine_phase2_adapter_base.py`
- `tests/test_phase2_strict_live_data_contract.py`
- `docs/agent_reviews/live_truth_28_strict_live_data_contract_phase2.md`

### Evidence Contract Fields

mode: LIVE
candidate_id: LIVE_TRUTH_28_STRICT_LIVE_DATA_CONTRACT_PHASE2
decision: PHASE2_STRICT_LIVE_DATA_CONTRACT
reason: LIVE Phase2 now marks candidates with absent quote age, absent spread/BBO context, absent liquidity validation, unknown quote source, or estimated RR context as non-executable with explicit blocker codes instead of applying executable-grade defaults.
timestamp: 2026-05-29T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live_truth_28_strict_live_data_contract_phase2.md

### Non-goals

- No broker calls.
- No live orders.
- No ranking weight tuning.
- No UI/dashboard changes.

## Grill Me Review

### Pushback

Filling fake defaults for quote age/spread/liquidity/RR can make a broken data path appear executable. LIVE must fail closed.

### Required proof

- Absent `quote_age_sec` in LIVE downgrades candidate to non-executable with visible blocker code.
- Absent spread/BBO context in LIVE downgrades candidate to non-executable with visible blocker code.
- Absent liquidity validation in LIVE downgrades candidate to non-executable with visible blocker code.
- Estimated RR context in LIVE downgrades candidate to non-executable with visible blocker code.
- PAPER/SIM behavior remains unchanged where supported.

## Hermes Review

### Contract clarity

`_apply_data_fallbacks(...)` remains a compatibility helper for non-LIVE modes, but in LIVE/REAL it becomes a strict contract enforcer by setting `execution_ok=False` and emitting explicit `execution_quality_reason_code` and `gate_reasons`.

### Safety boundary

No external calls are made. The change is deterministic and contained to Phase2 candidate shaping.

## GSD Review

### Minimality

- Changes are confined to Phase2 candidate shaping and do not touch strategy generation, execution router, or broker adapters.
- LIVE/REAL behavior is tightened only by converting absent/fallback data into explicit non-executable blocker codes.

### Determinism

All decisions are deterministic over the candidate payload + config flags; no time, network, or broker dependencies.

## QA / Safety Review

Tests assert:

- LIVE row with absent spread and BBO cannot become `ENTER` and carries `missing_spread_context`.
- LIVE row with absent quote age cannot become `ENTER` and carries `missing_live_timing_context`.
- LIVE row marked `rr_estimated_context` cannot become `ENTER` and carries explicit blocker code.
- PAPER rows still apply Phase2 fallback fields for watchlist/debug scoring.

## High-Risk Path Review

High-risk module touched: `core/_engine_phase2_adapter_base.py` (Phase2 decision pipeline).

Safety review notes:

- LIVE behavior is tightened only (fail-closed).
- No order placement or broker paths are modified.

## Scope Guard

Confirmed not touched:

- Broker adapters.
- Order/execution router.
- Strategy generation or ranking weights.
- UI/dashboard.

## Acceptance Proof

Run:

```bash
python -m py_compile core/_engine_phase2_adapter_base.py core/candidate_scoring.py
PYTHONPATH=. python -m pytest -q tests/test_phase2_strict_live_data_contract.py
PYTHONPATH=. python -m pytest -q tests/test_engine_phase2_adapter.py
```

Expected:

- LIVE strict data contract tests pass.
- Existing Phase2 adapter tests remain green.

## Runtime Proof Required After Merge

During a live observation window:

- Verify candidates with `phase2_spread_fallback_used` or `phase2_liquidity_fallback_used` do not become executable in LIVE.
- Verify candidates with absent quote age/spread/liquidity show explicit rejection/downgrade blocker codes.

## What This PR Does Not Prove

- It does not prove feed correctness or quote truth end-to-end.
- It does not prove broker/order safety (explicitly out of scope).

## Human Approval

Merge only if CI is green and reviewers confirm LIVE strictness increased (no new executable fallback paths).
