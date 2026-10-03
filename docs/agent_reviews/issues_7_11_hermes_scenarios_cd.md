# Hermes Contract — Issue 11 Scenarios C/D Observer Boundary

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**scope:** offline composition of feed-health producer output with the read-only strategy-shadow snapshot consumer for one stale derivative domain and one stale required spot domain
**requested_paths:** `tests/paper_shadow/test_issue11_scenarios_cd.py` and Issues 7–11 evidence artifacts
**forbidden_paths:** production runtime, candidate/ranking semantics, shared classifier semantics, broker/order/risk gates, credentials, token universe
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Contract and limits

Scenario C: when `INDEX_SPOT` is explicitly healthy and an exact, fresh NIFTY quote is present, the actual producer envelope may create a healthy **read-only observer snapshot** while `INDEX_OPTIONS` is degraded. A quote-dependent option snapshot must remain degraded. Scenario D: when required `INDEX_SPOT` health is degraded, the same quote must not create a healthy observer snapshot. Shared transport failure must keep it degraded in either case.

This contract does not prove an executable candidate, normal strategy evaluation, candidate-level fault isolation, or live behavior. Candidate dependency authority is incomplete and shared feed/candidate semantics remain unchanged. No production edits are authorized.

## Acceptance proof

1. Compose `build_feed_health_truth_latest_payload` with `StrategyMarketSnapshotBuilder.build_snapshots`; do not hand-build the producer envelope.
2. Assert exact NIFTY quote identity is joined, spot-only observation is healthy only with fresh quote plus healthy spot domain and explicit global-clear/connected transport evidence.
3. Assert stale option evidence keeps the option snapshot degraded and does not grant executable authority.
4. Flip the required spot domain to degraded, then separately transport to disconnected; the spot snapshot must stay degraded.
5. Assert no broker/order/paper/live authority is produced and clearly preserve candidate-level isolation as UNKNOWN.
