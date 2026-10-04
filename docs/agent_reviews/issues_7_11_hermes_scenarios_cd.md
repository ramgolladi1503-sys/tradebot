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

## Agent Work Contract

Campaign issue contract; see `issues_7_11_campaign_review.md` for the PR-level Hermes/GSD scope and actions.

## Scope Guard

Issue-level design boundary and restrictions are defined above; the consolidated review records the full campaign boundary.

## Grill Me Review

Campaign risk critique and unresolved proof limits are recorded in `issues_7_11_campaign_review.md`.

## Hermes Review

This file is the issue-specific Hermes contract. The consolidated review records the cross-issue architecture review.

## GSD Review

Execution evidence and test limits are recorded in `issues_7_11_campaign_review.md`; this contract alone is not implementation proof.

## QA / Safety Review

Safety boundary and verification limits are recorded in `issues_7_11_campaign_review.md`.

## High-Risk Path Review

See `issues_7_11_campaign_review.md` for the cross-cutting review of feed and orchestrator high-risk paths. This issue contract does not authorize runtime or broker actions.

## Acceptance Proof

Issue-specific acceptance criteria are defined above. Cross-issue executed proof and its limitations are recorded in `issues_7_11_campaign_review.md`.

## Runtime Proof Required After Merge

Runtime proof requirements are recorded in `issues_7_11_campaign_review.md`; offline contract text does not establish runtime parity.

## What This PR Does Not Prove

See the consolidated review for campaign-level limitations. This issue contract does not independently claim live verification.

## Human Approval

This design contract does not represent human approval. The PR remains subject to human review as described in `issues_7_11_campaign_review.md`.
