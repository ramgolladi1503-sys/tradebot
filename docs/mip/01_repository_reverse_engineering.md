# Agent 1 Report: Repository Reverse Engineering

## Current Architecture
The `tradebot` repository employs a highly modular, safety-first architecture designed to govern the full lifecycle of trading candidates from inception to execution. It operates on a strict pipeline where candidates must pass through multiple validation gates (Phase-1, Phase-2, readiness, health) before becoming executable.

## Lifecycles

### Candidate Lifecycle
Managed heavily through `core/candidate_pool.py`, `core/candidate_pool_orchestrator.py`, and `core/candidate_state_contract.py`.
Candidates are evaluated against strict `EXECUTABLE_STATE`, `RANKABLE_STATE`, `ADVISORY_STATE`, `DEBUG_ONLY_STATE`, `SOFT_REJECT_STATE`, and `HARD_REJECT_STATE` definitions. Any fallback data or missing liquidity validation forces a hard reject.

### Strategy Lifecycle
Handled in `core/strategy_lifecycle.py`, `core/strategy_lifecycle_states.py`, and `core/strategy_spec.py`. Strategies generate candidates which are subsequently handed off to the orchestrator. Signals without clear directions or from missing strategy families face soft rejection.

### Ranking Lifecycle
`core/candidate_ranking.py` and `core/ranking_orchestrator.py` sort executable candidates based on calibrated expectations and execution priority rules. Strict adherence to `execution_allowed` markers is required.

### Phase-2 Lifecycle
Governed by `core/engine_phase2_adapter.py` and `core/_engine_phase2_adapter_base.py`. This phase enforces deep checks, converting candidates to `ADVISORY_ONLY` if they fail certain readiness or execution permission criteria.

### Execution Lifecycle
Located in `core/execution_engine.py`, `core/execution_router.py`, `core/execution_guard.py`. Execution requires `execution_ok=True`. Anything labeled `advisory_only`, `queue_only`, or missing safety evidence is aggressively blocked.

### Replay Lifecycle
Managed via `core/replay_engine.py` and `core/replay_contract.py`, enabling rigorous backtesting of feed faults, regimes, and scoring schemas.

### Telemetry & Dashboard Lifecycles
`core/decision_telemetry.py` and related telemetry streams emit real-time decision paths, while rejecting telemetry maps out the exact block reasons for dashboards.

## Safety Boundaries
The core is laden with `_guard.py` and `_truth.py` scripts (`runtime_safety_boot_guard.py`, `pretrade_risk_engine.py`, `quote_truth.py`). They explicitly look for hardware, market, and data-level corruption, enforcing fail-closed behaviors.

## Current Extension Points
The presence of `core/advisory_schema.py` provides an excellent existing extension point. The schema supports an `ADVISORY_ONLY_ROW_KIND` and handles non-executable contexts gracefully. We can attach the Market Intelligence Platform (MIP) payload here as an extended `advisory_context` dictionary.

## Hardcoded Constants / Hidden Heuristics / TODOs
We must ensure no "fake edge" or magic probabilities are injected into scoring. The architecture already actively fights this (e.g., `strategy_weight_learning.py` vs fixed weights). The MIP must use strictly calibrated or `UNCALIBRATED` markers and never force an `execution_allowed` bypass.
