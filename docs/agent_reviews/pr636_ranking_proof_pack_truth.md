# PR 636 Agent Review Evidence

## Agent Work Contract
- source_agent: Codex
- action: fix_ci
- title: Tighten ranking proof-pack feed risk truth
- scope: candidate ranking proof pack, feed-state semantics, CI evidence, and unit-test stabilization
- requested_paths: core/orchestrator.py, core/feed_state_engine.py, core/kite_depth_ws.py, scripts/live_soak.py, scripts/live_soak_advanced.py, scripts/import_upstox_instrument_master.py, docs/strategy_module_taxonomy.md
- allowed_paths: same as requested_paths plus docs/code_excellence/reports/changed_paths.txt
- forbidden_paths: credentials, order placement, broker API wiring, live execution gates, unrelated strategy logic
- expected_tests: targeted unit tests and repo-wide evidence gates
- acceptance_proof: exact failing tests rerun locally and gate output inspected on the same SHA

## Scope Guard
- This PR stays read-only with respect to broker actions.
- No order placement, cancellation, or execution-path weakening.
- No live mode changes.

## Grill Me Review
- Candidate proof-pack and feed-state semantics must stay fail-closed.
- Any relaxation of blockers must be backed by an explicit test.
- No silent fallback is acceptable for missing credentials or stale option ticks.

## Hermes Review
- The candidate-to-ranking pipeline should remain deterministic and snapshot-bound.
- Ranking may classify surviving candidates, but the final execution firewall must remain separate.

## GSD Review
- Fix the code path, then verify with the exact failing tests.
- Keep changes small enough to audit in one pass.

## QA / Safety Review
- Verified locally:
  - decision DAG tests
  - live indicator readiness tests
  - orchestrator gate-once tests
  - feed runtime and restart semantics
  - path scanner
  - strategy taxonomy sync

## High-Risk Path Review
- `core/orchestrator.py`: startup now skips depth-WS initialization when credentials are unavailable in non-live test startup.
- `core/kite_depth_ws.py`: option feed blockers now preserve stale and recovery-blocked truth instead of normalizing to `OK`.
- `core/feed_state_engine.py`: compatibility marker added for existing runtime tests.
- `scripts/import_upstox_instrument_master.py`: path literals were converted to structured path construction.

## Acceptance Proof
- Targeted failing tests pass locally after the fixes.
- Repo-wide path scanner passes locally.

## Runtime Proof Required After Merge
- Re-run GitHub Actions on the updated SHA and confirm `unit_tests`, `agent-review-evidence`, and `code-excellence-gates` go green.

## What This PR Does Not Prove
- It does not prove live trading safety.
- It does not prove broker credentials exist in CI.
- It does not prove profitability.

## Human Approval
- Required before any live execution behavior is changed.

## Evidence Audit Fields
- mode: PAPER
- candidate_id: pr636-ranking-proof-pack
- decision: verified
- reason: evidence_pack_required
- timestamp: 2026-07-06T14:30:00Z
- is_order_action: false
- broker_api_called: false
- source: local_validation

## Traceability Checklist
- candidate generation evidence present
- ranking proof pack present
- execution firewall preserved
- feed-state semantics preserved
- path-hardening checks passing
