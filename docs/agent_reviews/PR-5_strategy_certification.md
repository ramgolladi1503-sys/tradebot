# Agent Work Contract
source_agent: Antigravity
action: PLAN_PR, GENERATE_PATCH, GENERATE_TESTS
title: Strategy Certification Engine (PR-5)
scope: Implement a read-only governance engine to verify strategy registry, truth, evidence, and statistics reports and generate a final CertificationState.
requested_paths:
  - core/strategy_certification/
  - tests/strategy_certification/
  - scripts/run_strategy_certification.py
allowed_paths:
  - core/strategy_certification/*
  - tests/strategy_certification/*
  - scripts/run_strategy_certification.py
  - docs/strategy_certification/*
  - core/strategy_truth/semantic_comparator.py
forbidden_paths:
  - main.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/*
expected_tests: Provide 30+ tests for the Gate classes, CertificationEngine, validation and report generators.
acceptance_proof: CI passes and gates produce expected MD outputs via the CLI wrapper.

# Scope Guard
All edits are isolated to `core/strategy_certification`, `tests/strategy_certification`, and `docs/strategy_certification`. A minor type hint fix was applied to `core/strategy_truth/semantic_comparator.py`. No runtime dependencies on broker, orders, or execution logic.

# Grill Me Review
CRITIQUE_SCOPE
The task was explicitly limited to governance logic and generating reports. No profitability or optimization code was touched or generated. The engine only asserts that "The available evidence currently satisfies the configured governance policy."

# Hermes Review
DESIGN_ARCHITECTURE
The engine uses a sequence of `Gate` classes (Registry, Truth, Evidence, Statistics, Risk) that consume outputs from other systems and produce a `GateResult`. `CertificationEngine` aggregates these and produces a `StrategyCertificationReport`. `ReportGenerator` produces Markdown files.

# GSD Review
GENERATE_PATCH
The models, types, and logic gates are strictly read-only and return dataclasses.

# QA / Safety Review
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
mode=PAPER
candidate_id=N/A
decision=certification
reason=governance logic update
timestamp=2026-06-27T06:30:18Z
source=agent_pr
The engine handles missing files by returning FAIL and degrades the certification state appropriately. Strict assertions prevent arbitrary certification upgrades.

# Acceptance Proof
Tests pass locally (`pytest tests/strategy_certification -q`). Static analysis passes (`ruff check`, `mypy`). The CLI runs and produces 10 Markdown files under `docs/strategy_certification`.

# Runtime Proof Required After Merge
N/A

# What This PR Does Not Prove
This PR does NOT prove that any strategy is profitable, robust, or has edge. It only verifies that evidence reports exist and satisfy pre-configured threshold statuses.

# Human Approval
All requirements implemented according to PR-5 mission description.
