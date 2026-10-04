# Hermes Addendum — Scenario A With Completed-Bar Store

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Extend Scenario A's clean store to include a verified completed bar
**scope:** offline test-only composition of synthetic T-1 heritage, one durable completed bar, and the real shadow registry pulse dispatch
**requested_paths:** `tests/test_market_heritage_graph.py` and Issues 7–11 evidence artifacts
**allowed_paths:** `tests/test_market_heritage_graph.py`, this addendum, the matching GSD plan, and campaign evidence artifacts
**forbidden_paths:** production runtime, strategy semantics, candidate/ranking logic, broker/order/risk/feed gates, credentials, token universe, live/paper enablement
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Design and invariants

The original Scenario A contract proves positive synthetic T-1 loader-to-registry dispatch beside an empty clean store. This addendum strengthens the store condition without changing the original proof's authority boundary: persist one deterministic synthetic NIFTY 1-minute bar through the public `MarketSessionStore.persist_completed_bar` API before the 09:16 synthetic pulse, reopen the store, and verify the completed row plus integrity. Dispatch the same healthy synthetic pulse through the actual registry and actual adapter methods.

The store is not injected into or read by the shadow registry/adapters in this test. Therefore the acceptance claim is coexistence of a clean durable completed-bar store with the verified T-1 adapter boot path; it does not prove that adapters consumed persisted bars, that C1/C2 was wired to this registry, or that candidates became eligible.

The bar must have positive, internally consistent OHLC, the fixture's exact 09:15 IST minute timestamp, explicit deterministic-test provenance, and `completed_as_of` exactly at 09:16 IST. The query must be as-of 09:16 and return that single completed row. No market-data file, runtime path, strategy threshold, or authority state is changed.

## Acceptance proof

1. Keep the original pinned synthetic manifest verification and READY status assertions for all three prerequisite-dependent strategies.
2. Persist one valid synthetic completed bar before pulse dispatch; require `INSERTED` and `persisted=true`.
3. Reopen an independent `MarketSessionStore`, require integrity `PASS`, and read exactly that bar at the 09:16 as-of boundary.
4. Run the actual registry pulse dispatcher and assert all three actual adapter methods are reached.
5. Assert evidence directories exist and broker/order/paper/live authority stays closed with all order counters zero.
6. Mark the proof as offline synthetic wiring only. Actual T-1 authority and actual consumer linkage remain UNKNOWN.

## Risks and limits

A passing test cannot establish captured T-1 source/calendar authority or that production evaluators read the durable store. Do not connect the store to registry state, add global runtime wiring, or infer candidate execution from adapter invocation.

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
