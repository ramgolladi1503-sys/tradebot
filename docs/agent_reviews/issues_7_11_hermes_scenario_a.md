# Hermes Contract — Scenario A Verified T-1 Clean Boot

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**scope:** offline positive wiring from independently verified synthetic T-1 heritage through the real shadow registry and pulse dispatcher, alongside a clean session store
**requested_paths:** `tests/test_market_heritage_graph.py` and Issues 7–11 evidence artifacts
**forbidden_paths:** production runtime, strategy semantics, candidate/ranking logic, broker/order/risk/feed gates, credentials, token universe, live/paper enablement
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Contract and limits

Use the repository's verified-manifest publisher/loader with a deterministic synthetic source fixture. The exact verified values must reach the real `StrategyShadowAdapterRegistry`; all three dependent adapters must register and receive a healthy source-time pulse through the normal registry dispatcher. An empty clean `MarketSessionStore` must report integrity PASS and no bars; no bar or signal is fabricated. Strategy outputs are not required.

This proves positive offline wiring only. It does not establish real October 1 input authority, a live clean boot, candidate eligibility, or strategy edge. No production code or threshold changes are authorized.

## Acceptance proof

1. Pin and independently verify the synthetic manifest; assert every strategy readiness is READY.
2. Construct the actual registry from loader output and assert all three adapters are registered, no dependent strategy is disabled, and evidence directories exist.
3. Dispatch an exact-identity healthy NIFTY spot/futures pulse through `registry.on_pulse`; prove every adapter receives the pulse through its actual evaluator method without requiring a generated signal.
4. Verify a clean empty durable market-session store and closed broker/order/paper/live authority.
5. Label every result fixture-only and retain actual T-1 source authority as UNKNOWN.

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
