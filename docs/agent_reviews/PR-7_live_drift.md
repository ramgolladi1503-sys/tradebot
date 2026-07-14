# Agent Work Contract
- **source_agent**: Antigravity
- **action**: PLAN_PR, GENERATE_PATCH, GENERATE_TESTS
- **title**: PR-7 — Live Drift & Certification Lifecycle Engine
- **scope**: Build a read-only governance layer connecting certified expectations to live observed performance.
- **requested_paths**: `core/live_drift/`, `tests/live_drift/`, `docs/live_drift/`, `scripts/run_live_drift.py`
- **allowed_paths**: `core/live_drift/`, `tests/live_drift/`, `docs/live_drift/`, `scripts/run_live_drift.py`
- **forbidden_paths**: All other paths.
- **expected_tests**: > 40 tests covering drift logic, no fake confidence.
- **acceptance_proof**: Tests pass, CE gates pass, script generates 10 Markdown files, no execution mutation.

# Scope Guard
All modifications were rigidly constrained to `core/live_drift`, `tests/live_drift`, `docs/live_drift`, and `scripts/run_live_drift.py`. No runtime strategy or broker integrations were mutated.

# Grill Me Review
CRITIQUE_SCOPE
The PR creates a purely read-only engine. It enforces rigid state tracking via `frozen=True` dataclasses and enum-driven logic. There is no strategy re-optimization, backtesting, or execution logic. It solely produces governance recommendations based on deterministic thresholds.

# Hermes Review
DESIGN_ARCHITECTURE
The engine uses `DriftDetector` to coordinate modular drift checks (`PerformanceDriftChecker`, `RegimeDriftChecker`, `ExecutionDriftChecker`, `FreshnessChecker`). The `NotificationEngine` emits immutable `ActionRecommendation`s based on severity scores, feeding into `CertificationLifecycle` state tracking.

# GSD Review
GENERATE_PATCH
I generated the required models, loaders, detectors, lifecycle management, and logging architecture. The script outputs the 10 requested Markdown files detailing the differences between certified baseline and current snapshot without stating profitability claims.

# QA / Safety Review
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
mode: PAPER
candidate_id: N/A
decision: drift_monitoring
reason: build baseline observability
timestamp: 2026-06-27T12:00:00Z
source: agent_pr
The PR performs strictly offline static data monitoring.

# Acceptance Proof
Tests cover all drift paths (e.g. Expectancy Collapse), stale evidence, invalid transitions, and audit logging. 45 robust tests implemented.

# What This PR Does Not Prove
- Does not prove that the underlying baseline statistics are correct.
- Does not automatically suspend any live strategy (only outputs recommendations).

# Human Approval
- Approved via user's explicit request and plan approval.

# Runtime Proof Required After Merge
- None.


## Agent Work Contract

N/A

## Scope Guard

N/A

## Grill Me Review

N/A

## Hermes Review

N/A

## GSD Review

N/A

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
