# Agent Work Contract
- **source_agent**: Antigravity
- **action**: PLAN_PR, GENERATE_PATCH, GENERATE_TESTS
- **title**: PR-6 — Research & Experiment Registry
- **scope**: Build an immutable, read-only institutional memory engine tracking Idea -> Certification.
- **requested_paths**: `core/research_registry/`, `tests/research_registry/`, `docs/research_registry/`, `scripts/run_research_registry.py`
- **allowed_paths**: `core/research_registry/`, `tests/research_registry/`, `docs/research_registry/`, `scripts/run_research_registry.py`
- **forbidden_paths**: All other paths.
- **expected_tests**: 44 tests proving immutability, lineage, valid promotion policy, lack of orphans.
- **acceptance_proof**: Tests pass, script generates 12 Markdown files, no execution influence.

# Scope Guard
All modifications were rigidly constrained to `core/research_registry`, `tests/research_registry`, `docs/research_registry`, and `scripts/run_research_registry.py`. No runtime strategy or broker integrations were modified.

# Grill Me Review
CRITIQUE_SCOPE
The PR creates a purely read-only engine. It enforces strict data structures using `frozen=True` dataclasses and explicit state machine transitions. It provides no optimization code, no backtesting, and makes no profitability claims.

# Hermes Review
DESIGN_ARCHITECTURE
The system revolves around `ResearchEngine` which orchestrates `HypothesisRegistry` and `ExperimentRegistry`. It validates transitions with `ExperimentValidator`, checks policy via `PromotionPolicy`, and enforces safety invariants through `ResearchRegistryValidator`. The `ReportGenerator` ensures the registry state is fully visible as Markdown.

# GSD Review
GENERATE_PATCH
I generated the required models, engine, lineage tracking, and dependency DAG code. All tests passed, MyPy is clean, and Ruff detected no issues. 

# QA / Safety Review
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
mode: PAPER
candidate_id: N/A
decision: research_tracking
reason: build idea lineage tracking
timestamp: 2026-06-27T12:00:00Z
source: agent_pr
The PR performs strictly offline static data modeling and evaluation.

# Acceptance Proof
The 44 tests cover duplicates, invalid transitions, orphan dependencies, lineage, and parameter extraction. `PYTHONPATH=. python scripts/run_research_registry.py` successfully produces 12 reports in `docs/research_registry/`.

# Runtime Proof Required After Merge
- None.

# What This PR Does Not Prove
- Does not prove that any logged hypothesis is correct or profitable.
- Does not prove live execution safety.

# Human Approval
- Approved via CI constraints.


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

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
