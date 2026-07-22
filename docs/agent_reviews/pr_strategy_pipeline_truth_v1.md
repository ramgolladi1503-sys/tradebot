# Exact Truth Pipeline Stage Review

mode: RESEARCH
candidate_id: STRATEGY_PIPELINE_TRUTH_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Replace scan-all and exit-code Truth execution with one exact Registry-backed implementation audit, a separate AST oracle, and hash-verified blocked diagnostics.
timestamp: 2026-07-22T19:25:00Z
is_order_action: false
broker_api_called: false
source: agent/strategy-pipeline-truth-v1

## Agent Work Contract

Implement only the Truth-stage repair above draft PRs #700 and #701. Truth must consume exactly the signed Registry result manifest for the same strategy and pipeline run. It must independently verify the Registry artifact, implementation-file hash, canonical contract hash, declared strategy identity, and current source before running the existing Truth scanners and auditors on exactly one implementation. Success requires both the existing audit verdict and an independent AST structural oracle to pass with no residual audit blockers.

## Scope Guard

In scope: exact Truth adapter, independent AST oracle, canonical Truth-script pipeline routing, verified mismatch diagnostics, blocked-artifact support in the shared adapter runtime, and Truth-focused tests.

Out of scope: changes to strategy behavior, thresholds, signal formulas, market data, option replay, costs, statistics, WFA, holdout, certification, Drift, broker APIs, order execution, risk, feeds, credentials, or dashboards.

The implementation reuses existing `core/strategy_truth` components; it does not replace their general non-pipeline command behavior.

## Grill Me Review

- Can Truth scan all strategies and select a convenient report? No. Pipeline mode accepts exactly one signed `registry.result.json`.
- Can the strategy file change after Registry succeeds? No. Truth recomputes the implementation SHA-256 and blocks on any difference.
- Can a forged contract inside the Registry artifact pass? No. Truth recomputes the canonical contract hash and reconstructs a validated `StrategyManifest`.
- Can the old Truth verdict alone grant success? No. The independent AST oracle must also pass and the existing audit must have no indicator, dependency, semantic, mathematical, heuristic, or rule blockers.
- Can direct broker or order coupling pass? No. The independent oracle rejects direct order calls and broker/execution imports.
- Can a mismatch disappear because the stage blocks? No. Truth writes `truth.stage.json`; the BLOCKED result includes and hash-verifies that diagnostic artifact.
- Does Truth success prove profitability? No. It proves only declared implementation structure and lineage.

## Hermes Review

Truth runs only in `RESEARCH` or `PAPER` mode through the already validated adapter runtime. It reads the declared strategy source and upstream artifacts but does not import broker clients for action, place orders, mutate strategy configuration, or grant live authority. The legacy standalone Truth command remains available when pipeline environment variables are absent.

## GSD Review

The previous pipeline launched a scan-all Truth script, trusted its process exit code, and recorded no exact report artifact. The new pipeline route binds one Registry manifest, one implementation hash, one contract hash, the existing Truth component outputs, an independent oracle result, explicit blockers, and a signed result manifest. Only `IMPLEMENTATION_VERIFIED` with a passing oracle and zero audit blockers can continue to Outcomes.

## QA / Safety Review

Local isolated validation:

- `PYTHONPATH=. pytest -q tests/strategy_pipeline/test_pipeline_engine.py tests/strategy_pipeline/test_pipeline_blocked_artifacts.py tests/strategy_pipeline/test_research_registry_stage_adapters.py tests/strategy_pipeline/test_truth_stage_adapter.py tests/strategy_pipeline/test_truth_fail_closed_edges.py` -> `38 passed`.

A full-repository integration smoke test is also included at `tests/strategy_pipeline/test_truth_existing_engine_integration.py`. It invokes the actual existing Truth scanners, rule extractor, parameter and heuristic auditors, dependency analyzer, control-flow reconstructor, semantic comparator, mathematical auditor, and implementation auditor on exactly one fixture. That test must pass in repository CI before this PR is acceptable.

Covered isolated cases include Oracle ORB success, missing-window failure, direct order-call failure, exact Registry lineage, contract deserialization, implementation mutation after Registry, extra undeclared inputs, successful combined audit/oracle result, residual-blocker rejection despite a verified label, and hash-verified mismatch diagnostics.

## Acceptance Proof

Acceptance requires the 38-test isolated suite, the real existing-engine integration smoke, Python compilation, all repository workflows, and all parent-stack workflows to pass on immutable heads. A mismatch, partial verification, manual-review verdict, unknown oracle paradigm, direct broker coupling, contract hash mismatch, changed implementation, or residual audit blocker must prevent Truth SUCCESS.

## Runtime Proof Required After Merge

Run one disposable governed pipeline through Research and Registry, then execute Truth using the automatically chained Registry manifest. Retain the Truth stage artifact and result manifest. Confirm that a deliberately changed strategy source produces `TRUTH_STAGE_BLOCKED` or `IMPLEMENTATION_NOT_VERIFIED`, while the diagnostic artifact remains hash-valid. Outcomes must remain unavailable until Truth produces verified SUCCESS.

## What This PR Does Not Prove

This PR does not prove structural edge, positive expectancy, realistic fills, correct option traces, transaction costs, statistical significance, WFA stability, holdout performance, certification readiness, paper performance, or live performance. It does not repair Outcomes, Statistics, Certification, or Drift.

## Human Approval

Human review is required before merge. This stacked PR grants no paper or live trading authority, performs no automatic merge or deployment, and cannot create an order action.
