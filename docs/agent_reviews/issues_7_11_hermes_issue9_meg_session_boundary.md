# Hermes Stage 1 — Issue 9 MEG shadow-buffer session boundary

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Keep the read-only MEG candle view inside the `as_of` IST date
**scope:** `core/market_event_graph_live_ohlc_buffer.py` and its focused tests. Follow-up to `issues_7_11_hermes_issue9_same_process_session_isolation.md`.

## Reproduction and root cause

With the MEG shadow store disabled, put two completed bars on 2026-09-07 and a new-session tick on 2026-09-08 into the actual shadow `OhlcBuffer`. `get_live_source_shadow_completed_bars(..., as_of=2026-09-08 09:16 IST)` returns both 2026-09-07 bars as well as the current-session bar. With a configured store, `persist_completed_live_source_shadow_bars` returns without persistence when the cutoff date differs from `_SESSION_DATE`, but the caller still returns the unfiltered process-local buffer.

This is an observer-only Issue 9 repository defect. The shadow buffer is isolated from strategy OHLC, but stale-date bars can contaminate MEG snapshots and evidence.

## Contract

`get_live_source_shadow_completed_bars` must return only bars whose timestamps, converted to Asia/Kolkata, have the same local date as the requested `as_of`. Preserve existing bar completion filtering, persistence ordering, buffer contents, provenance, and the no-write/no-decision boundary. Do not clear the buffer or claim filtered historical rows are persisted. Store configuration and exact session authority remain governed by existing code.

No changes to feed subscription/recovery, source identity, CAS, strategy, ranking, persistence schema, token universe, risk, execution, broker/order, or live authority.

## Acceptance

1. Reproduce RED with the real shadow buffer and disabled session store.
2. After repair, D+1 observer output contains only D+1 completed bars; the buffer itself remains unchanged.
3. A temporary-copy mutation removing only the returned-row date filter fails at the exact timestamp assertion.
4. Existing MEG live OHLC buffer and runtime bridge tests pass.

## Safety

Read-only observer view. `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`. No broker, order, or live operations.

## GSD verification update

The actual D-to-D+1 regression failed before the filter and passed after. The targeted MEG buffer/runtime bridge suite passed **45 tests**, and a temporary-copy mutation removing only the return-date predicate failed at the exact expected timestamp assertion. Fresh independent review found no P1/P2 issue and confirmed ingress timezone canonicalization plus preservation of the buffer and persistence ordering. This remains offline observer evidence only.

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
