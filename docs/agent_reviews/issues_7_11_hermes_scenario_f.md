# Hermes Contract — Cross-Issue Scenario F: Missing T-1

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**requested_paths:** offline T-1 loader and shadow-registry integration test plus Issues 7–11 evidence artifacts
**forbidden_paths:** production runtime, strategies, candidate/ranking semantics, broker/order/risk/feed gates, credentials, token universe
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Repository facts

`core/market_heritage_graph.py::load_verified_t1_prerequisites` requires an explicitly pinned manifest under an approved root, verifies the artifact and heritage graph, and returns null values with a structured blocked result when no pinned manifest is supplied. `core/kite_read_only_observation_runtime.py` passes this report to `StrategyShadowAdapterRegistry`. The registry disables the three registered T-1-dependent shadow strategies when their prerequisites are not ready and writes both disabled reasons and the prerequisite report to `registry.json`.

Repository-local historical audit `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/T1_AUTHORITY_FORENSICS.md` records that the observed 2026-09-30 sources do not establish exact futures 15:29 source-event authority or the 200-session daily-close ancestry. A separate read-only audit of current repository artifacts confirms that the old 2026-09-23 preflight is inventory-only and cannot satisfy current pinned-manifest requirements. Therefore the original live-session T-1 values remain `UNKNOWN`; this scenario exercises the safe missing-source behavior and does not claim the historical cause is repaired.

## Contract

When no pinned T-1 manifest is available, the actual loader output must remain blocked and nullable. The shadow registry must disable each T-1-dependent adapter, persist the exact loader-level blocker in its prerequisite-verification telemetry, and preserve closed authority flags. No guessed close, SMA, futures contract, calendar ancestry, candidate, or entry eligibility may appear.

This is an offline integration proof for Scenario F only. It does not establish positive source admission, calendar holidays, Issues 8 recovery, unrelated live strategy continuity, or captured/live behavior.

## Acceptance proof

1. Call the actual loader with absent manifest path/hash using the same three strategy contracts and instrument identities as the read-only observer.
2. Feed its returned values and verification report into the actual registry constructor.
3. Assert all required T-1 values remain `None`; all three dependent adapters are absent and carry deterministic fail-closed reasons.
4. Assert `registry.json` preserves the precise loader reason and all authority flags remain closed with zero order counters.
5. Attack the test by substituting non-null legacy values while readiness is absent/blocked; the registry must remain disabled.

No production files or strategy contracts are authorized by this Scenario F contract.

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
