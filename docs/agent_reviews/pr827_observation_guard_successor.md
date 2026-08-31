# PR827 Minimal Observation-Execution Guard Successor

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Add a fail-closed observation-only execution boundary
- scope: current-main execution boundaries only
- requested_paths: `core/observation_execution_guard.py`, `core/execution_adapter.py`, `core/execution_engine.py`, `core/broker/mock_broker.py`, `tests/test_observation_execution_guard.py`
- allowed_paths: the five implementation/test paths above, plus this review record
- forbidden_paths: broker credentials, live runtime launchers, evidence artifacts, stale clean-observation launcher, strategy and risk thresholds
- broker_connectivity_authorized: false
- broker_write_authority: false
- order_authority: false
- paper_authorized: false
- live_execution_authorized: false
- expected_broker_methods: none
- forbidden_broker_methods: all broker write/order/position/funds methods
- credential_boundary: no credentials or tokens read or persisted

## Design and Scope

Current `main` lacked a shared observation-only execution guard at the three real boundaries: `ExecutionEngine.place_order`, `AdvancedExecutionAdapter.execute_limit_hunt`, and `MockBroker.place_order`. This successor adds one dependency-light environment gate and invokes it before any order intent, thread, sequence, event, or broker state mutation.

The stale clean-observation launcher and its tests are intentionally excluded. No synthetic modify/cancel methods are added because current `main` does not expose those entry points.

## Safety Contract

Observation-only mode dominates `ALLOW_LIVE_PLACEMENT`, `LIVE_TRADING_ENABLED`, `PAPER_TRADING_ENABLED`, `AUTO_TRADE`, and `AUTO_ORDER`. When enabled, the guard raises `ObservationOnlyExecutionBlocked` with the exact guarded boundary. When disabled, the guard is a no-op. It performs no broker calls and has no import-time side effects.

## Acceptance Proof

- focused guard tests: required
- unit tests: required
- safety tests: required
- gitleaks: required
- CodeQL: required
- repo forensics: required
- broker API calls: 0
- orders placed/modified/cancelled: 0

## What This Does Not Prove

This offline change does not authorize paper or live execution, establish broker connectivity, or constitute live-market evidence. Any later runtime promotion requires its separate human-controlled authority and evidence gates.
