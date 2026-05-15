# CI Compatibility Hook Cleanup Plan

## Purpose

PR #35 got the reliability baseline green, but it did so with stacked import-time compatibility hooks. That was acceptable as an emergency stabilization step, not as long-term architecture.

This document tracks the cleanup plan so the repo does not quietly normalize runtime behavior through `sitecustomize.py` and `core/ci_*_contracts.py` modules.

## Current debt

`sitecustomize.py` currently installs the following runtime hooks:

- `core.ci_compat_contracts`
- `core.ci_last_contracts`
- `core.ci_final_contracts`
- `core.ci_tail_contracts`
- `core.ci_finish_contracts`
- `core.ci_last5_contracts`

Previously removed/deactivated:

- `core.ci_phase2_final_contract` was removed in PR #37 after Phase2 adapter behavior moved into `core/engine_phase2_adapter.py`.
- Phase2 behavior in `core.ci_last5_contracts` was deactivated in PR #37.
- Depth behavior in `core.ci_finish_contracts` and `core.ci_last5_contracts` is targeted by PR #38 after confirming the owning module already carries the subscription contracts.

These modules should not remain as permanent product behavior. Each hook must either be:

1. moved into the real owning module with explicit tests, or
2. deleted if it only patched obsolete test assumptions.

## Cleanup rules

- Do not delete all compatibility modules in one PR.
- Do not touch trading behavior and cleanup behavior in the same PR.
- Each cleanup PR must keep `tests`, `ci`, `Portfolio CI`, and `CodeQL Advanced` green.
- Each migration must name the owning module and the test group it protects.
- If deleting a hook turns CI red, the hook is hiding a real contract that must be implemented directly.

## Migration order

### 1. Phase2 adapter contracts — completed in PR #37

Owning module:

- `core/engine_phase2_adapter.py`

Absorbed/deactivated behavior:

- dynamic spread threshold
- off-hours spread multiplier
- strict real-candidate filtering
- playbook-required filtering
- split-brain quote protection
- unresolved-contract hard blockers

Exit gate:

- Phase2 adapter tests pass without `ci_phase2_final_contract` and without Phase2 sections in `ci_last5_contracts`.

### 2. Depth subscription contracts — PR #38

Owning module:

- `core/kite_depth_ws.py`

Real-module behavior to own:

- NIFTY minimum option floor
- stale option pruning
- stale-prune hysteresis
- session-tick-required behavior
- `final_option_count` resolution metadata
- monkeypatch-safe startup token resolution

Exit gate:

- Depth subscription and orchestrator depth startup tests pass without depth sections in `ci_last5_contracts`, `ci_finish_contracts`, and related earlier hooks.

### 3. Freshness/readiness contracts

Owning modules:

- `core/freshness_sla.py`
- `core/readiness_gate.py`

Likely hooks to absorb:

- `no_ticks_yet` reason reporting
- stale-token accounting
- market-open blocked/ready state transitions
- feed-health runtime snapshot interpretation

Exit gate:

- Freshness SLA and readiness state-machine tests pass without freshness/readiness hook sections.

### 4. TradeBuilder contracts

Owning module:

- `strategies/trade_builder.py`

Likely hooks to absorb:

- soft-veto reason precedence
- borderline no-signal fallback behavior
- blocked candidate reason payloads
- high-OI stale soften flags
- native telemetry payload detail

Exit gate:

- TradeBuilder tests pass without TradeBuilder compatibility sections.

### 5. Opportunity engine contracts

Owning module:

- `core/opportunity_engine.py`

Likely hooks to absorb:

- selected execution slots
- `slot_id`
- advisory/executable separation
- planning-only truth blocking
- ranking drift logging

Exit gate:

- Opportunity-engine selection and truth-guard tests pass without opportunity compatibility sections.

## Target final state

`sitecustomize.py` should contain only the pandas `freq="T"` compatibility patch, or be removed entirely if no longer needed.

All `core/ci_*_contracts.py` files should be deleted after their behavior is either implemented in real modules or proven obsolete.

## Non-goals

- No strategy expansion.
- No profitability changes.
- No live broker behavior changes.
- No bypassing branch protection.
