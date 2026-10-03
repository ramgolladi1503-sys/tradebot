# Hermes contract — Issue 7 NSE F&O holiday alignment

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Use one verified NSE F&O holiday set across preflight, session state, and expiry selection
**scope:** Correct the proven 2026 calendar omissions by moving the existing versioned NSE F&O holiday set to `core.market_calendar` and making the live-session preflight import it. Include the later January 15, 2026 exchange amendment.
**requested_paths:** `core/market_calendar.py`, `scripts/run_market_event_graph_live_session_v1.py`, `tests/test_market_session_state.py`, `tests/test_market_event_graph_live_session_preflight.py`, `tests/test_expiry_selection.py`, `tests/test_market_heritage_graph.py`
**allowed_paths:** requested source/tests, this contract, its GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** broker/order/risk/feed behavior, credentials, strategy thresholds, token-universe configuration, T-1 value generation/staging, network retrieval at runtime.
**expected_tests:** every source-listed 2026 NSE F&O holiday is recognized by shared holiday membership and preflight; January 15 amendment is recognized; March 3 mid-session policy is `MARKET_CLOSED`; expiry selection skips March 3; Monday/weekend and post-holiday predecessor tests still resolve from explicit verified records.
**acceptance_proof:** official holiday set is represented once and imported by both paths; focused tests pass; temporary naive calendar-day mutant remains killed; no data is fabricated or staged.

## Evidence and blast radius

Repository code had two calendar authorities. `scripts/run_market_event_graph_live_session_v1.py` contained NSE/FAOP/71777's 2026 F&O holiday list, while `core.market_calendar.IN_HOLIDAYS` omitted March 3, March 26, April 14, November 10, and the later January 15 amendment. `core.market_session_state` and expiry selection consume the latter, so they could treat listed exchange closures as open/non-holidays. NSE's official 2026 calendar lists March 3 as Holi and January 12 circular FAOP/72262 adds January 15 as an F&O holiday.

The patch is deliberately limited to shared calendar data and preflight reuse. It makes session state and expiry selection respect those documented closures. It does not redefine target trading-date authority, verify the completeness of future calendar years, establish futures source lineage, stage T-1 values, or alter candidate/strategy rules.

## Safety and rollback

No broker/order calls or live-process operations. No new config keys. Rollback restores the duplicated preflight constant and removes the five omitted dates plus Jan 15 from shared membership; that returns the known false-open/missed-holiday behavior. Keep Issue 7 market-data/source authority `UNKNOWN` until exact target-session futures evidence is available.

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
