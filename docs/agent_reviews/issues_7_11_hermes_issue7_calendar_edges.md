# Hermes contract — Issue 7 explicit calendar edge tests

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Prove T-1 resolver skips weekends and exchange holidays from explicit authority
**scope:** Offline tests and a temporary-copy mutation for `resolve_previous_eligible_session`.
**requested_paths:** `tests/test_market_heritage_graph.py`
**allowed_paths:** the requested test, `scripts/verify_issues_7_11_issue7_mutations.py`, this contract, its GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production source/runtime wiring, external data files, broker/order/risk/feed paths, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** a Monday target resolves Friday from explicit eligible-session records; a Wednesday target after an explicitly ineligible exchange holiday resolves the preceding eligible Monday. A temporary naïve calendar-day subtraction mutant must fail.
**acceptance_proof:** both expected predecessor dates resolve exactly; test remains based on explicit calendar authority and never derives a source price or prerequisite value.

## Invariant

The resolver must select the latest strictly earlier record that is explicitly `eligible=true` and `verified=true`, matching the target calendar ID/version, venue, and instrument ID. It must not infer a trading session from weekday arithmetic. A false or absent calendar authority remains blocked.

## Limits

These cases prove resolver behavior for supplied records only. They do not certify that the external calendar source is complete/correct for every date, establish futures data authority, stage T-1 values, or prove live prerequisite readiness. No production behavior changes are authorized.

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
