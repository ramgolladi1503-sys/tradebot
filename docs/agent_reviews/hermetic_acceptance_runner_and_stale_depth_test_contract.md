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
