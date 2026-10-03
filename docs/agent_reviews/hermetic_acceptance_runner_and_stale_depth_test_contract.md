# Hermetic Acceptance Runner and Stale-Depth Test Contract

## Hermes Work Contract

- `source_agent: hermes`
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS`
- `title: Make isolated acceptance commands reproducible and align stale-depth assertion with fail-closed behavior`
- `scope: Resolve the active Python interpreter in the credential-isolated acceptance environment without inheriting Python path variables; require aggregate feed freshness to include depth freshness; use canonical feed artifacts in the integration test and require stale depth to block both candidate emission and aggregate freshness.`
- `requested_paths: core/agent_supervisor_git.py; core/runtime_feed_truth_snapshot.py; tests/test_agent_supervisor.py; tests/integration/test_feed_truth_to_candidate_pipeline.py; tests/test_runtime_feed_truth_snapshot.py; docs/agent_reviews/hermetic_acceptance_runner_and_stale_depth_test_contract.md`
- `allowed_paths: exactly the requested paths`
- `forbidden_paths: credentials and environment files; broker/order/execution/risk/strategy code; feed freshness gates or candidate qualification behavior; runtime session data; unrelated files`
- `expected_tests: acceptance command resolves to the current interpreter when executable is python; ignored credentials remain absent; inherited PYTHONPATH remains absent; fresh depth permits aggregate freshness only when all other inputs are fresh; stale or absent depth blocks aggregate freshness and candidate emission; canonical source artifacts pass provenance validation.`
- `acceptance_proof: sanitizer adds only the current interpreter's executable directory to PATH while preserving secret removal, isolated HOME, proxy closure, and explicit execution-safety flags; aggregate `feed_fresh` is true only when websocket, market-open, underlying tick, option tick, and depth are fresh; stale-depth replay emits no candidate and records stale depth; focused tests pass.`

## Design and Risk Boundary

The supervisor currently strips `PYTHONPATH` and isolates `HOME`, then resolves accepted command names using the remaining PATH. On installations where the running Python is available to the parent by absolute path but the sanitized PATH does not contain its directory, the permitted `python -m pytest` command fails with exit 127. Add the directory containing `sys.executable` to the sanitized PATH, keeping the contract's command allowlist and command-name-only restriction. Do not inherit Python module paths, user site configuration, credentials, or environment files.

The previous aggregate freshness formula omitted depth while the same snapshot emitted a `depth_stale_or_missing` reason. This let `feed_fresh=true` coexist with `depth_fresh=false`. Include depth freshness in aggregate feed freshness. The stale-depth integration test must use valid canonical artifacts (otherwise fail-closed provenance validation correctly treats the fixture as unknown) and assert an empty candidate result plus the emitted truth fields (`ws_connected`, fresh option tick, stale depth, stale aggregate feed, and the stale-depth reason).

Safety invariants remain `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`. No configuration keys or runtime wiring change.

## Agent Work Contract

Hermes defines the invariant contract above; GSD owns implementation and test verification within the listed paths.

## Scope Guard

The only runtime truth change is to require fresh depth in aggregate `feed_fresh`. Existing per-component depth status and option/underlying freshness remain visible. Acceptance environment repair changes PATH by one explicit executable directory; it does not restore credentials, HOME, Python module paths, or network access.

## Grill Me Review

- A malformed feed fixture is not valid evidence; use canonical artifacts and lineage.
- A stale depth field coexisting with `feed_fresh=true` is contradictory aggregate readiness.
- Do not make stale-depth candidates pass to satisfy an assertion; the candidate must remain blocked.
- Do not broaden sanitized environment variables beyond the current interpreter executable path.

## Hermes Review

Aggregate feed freshness requires websocket connectivity, market open, fresh underlying ticks, fresh option ticks, and fresh depth. Stale or missing depth keeps `depth_fresh=false`, adds the existing stale reason, and makes `feed_fresh=false`.

## GSD Review

GSD included the depth freshness predicate, canonical fixture provenance, a no-candidate stale-depth integration check, direct fresh/stale/missing-depth unit tests, and an acceptance runner test proving command resolution to `sys.executable` while ignored `.env` and inherited `PYTHONPATH` remain absent.

## QA / Safety Review

The behavior is stricter and fail-closed. No broker/order/risk/strategy behavior changes. Tests are offline; no production artifact is modified.

## Acceptance Proof

The combined focused suite passes. Fresh depth permits aggregate freshness only when the other feed inputs are fresh; stale or absent depth makes aggregate freshness false and the candidate result empty. The credential-isolated command runner test passes with an ignored source `.env` absent and isolated Python path.

## Runtime Proof Required After Merge

Read-only runtime evidence must show matching depth age, depth SLA, component freshness, and aggregate `feed_fresh` for the exact deployed producer SHA. This code-level check does not prove the persistence writer has no loss.

## What This PR Does Not Prove

It does not prove sustained depth ingestion, queue durability, option identity correctness by itself, or a clean full-repository suite on every supported host.

## Human Approval

Human review is required before merge or runtime rollout. No execution authority is granted.
