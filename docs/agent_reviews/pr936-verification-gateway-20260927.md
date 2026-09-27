# PR #936 verification-gateway review evidence

## Agent Work Contract

source_agent: hermes_then_gsd
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
title: Reuse-first verification gateway prototype and acceptance evidence
scope: Isolated research verification code, synthetic tests, and documentation in PR #936.
requested_paths: `research/verification_gateway/`, scoped research tests, `core/research_pipeline.py` Monte Carlo diagnostic only, and supporting documentation.
allowed_paths: Those scoped files only.
forbidden_paths: Broker/order/risk/feed/live paths, credentials, protected datasets/outcomes/runtime artifacts, CI workflow and root dependency manifests.
expected_tests: Synthetic schema, contract, reference-math, reference-execution, registry bridge, and seeded Monte Carlo tests.
acceptance_proof: Dependency-isolated gateway suite and Monte Carlo suite pass; verifier remains fail-closed; readiness state remains blocked where evidence is missing.

## Scope Guard

The canonical checkout was preserved; implementation took place in the managed isolated worktree. No broker API, order action, protected outcome, runtime ledger, live/paper path, credential, CI workflow, or root dependency manifest was accessed or changed. Output safety invariants: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.

## Grill Me Review

Independent read-only review found two correctness defects. First, an exit replay chose the earliest quote after the exit decision and then rejected it if it had been published before entry fill availability, even where a later eligible quote existed. The selector now filters on availability strictly after the entry fill, with a regression containing both quotes. Second, OHLCV fixture validation allowed non-finite numeric values and blank or untrimmed identity values to reach shape validation. Boundary checks now reject those inputs with explicit errors and tests. The reviewer also found stale CI wording; the readiness report now records five collection errors.

## Hermes Review

The design keeps source fidelity, data authority, execution parity, and release authority separate. Caller-provided pass flags and reviewer strings cannot self-certify a strategy. Synthetic data shape and replay remain explicitly non-authoritative for provenance or historical execution. The independent review defects and corrective constraints are documented above and in the scoped acceptance tests.

## GSD Review

Scoped remediation is implemented. Gateway, registry, reference mathematics, data shape, and synthetic execution tests pass using the documented isolated research dependency set. The replay now selects the first eligible exit quote only after both exit-decision eligibility and entry-fill availability. OHLCV nonfinite/identity cases are rejected before Pandera coercion. Monte Carlo tests remain unchanged and pass.

## QA / Safety Review

Validation: 52 gateway tests passed (one pytest cache warning) in `/tmp/pr936-verification-venv`; 9 Monte Carlo tests passed (one pytest cache warning) in the system Python environment. These local runs used only inline synthetic fixtures. The live remote CI result remains failed at collection because the protected default workflow does not install Pydantic. No CI failure was bypassed or hidden. Full project test suite, OS-level protected-path denial, API bypass prevention, and production backtest parity are not established.

## Acceptance Proof

The exact local test command is recorded in `research/verification_gateway/ACCEPTANCE_TEST_LOG_20260927.txt`. Independent review findings have matching regression coverage. The code still reports `BLOCKED_WITH_EXACT_DEPENDENCY`; no controlled research release is claimed.

## Runtime Proof Required After Merge

No runtime proof is claimed or appropriate for this offline-only prototype. Any later runtime integration requires an explicitly scoped and separately approved design, read-only boundary proof, and exact-SHA validation before use.

## What This PR Does Not Prove

This PR does not prove source-strategy fidelity, authenticated source review, point-in-time or survivorship authority, historical quote validity, fills or costs in production, dependence-aware inference, a complete trial denominator, a complete official-entrypoint call graph, OS-enforced protected-data denial, or an edge. `NO_CERTIFIED_EDGE` remains the only supported strategy disposition.

## Human Approval

Human approval is still required for any protected CI/dependency integration and for later runtime or data-authority wiring. The current draft PR is not merge-ready for controlled discovery; its exact verdict remains `BLOCKED_WITH_EXACT_DEPENDENCY`.
