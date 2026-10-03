# Hermes Stage 1 — Issue 9 strategy memory runtime bridge

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Connect canonical completed-bar persistence to causal C1/C2 memory reads
**scope:** Offline implementation and tests in the isolated worktree. No broker/order/live actions.
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Root-cause evidence

The regular market-data path calls `core.ohlc_buffer.ohlc_buffer.update_tick` (`core/market_data.py`), while C1/C2 calls `_global_market_session_store.get_market_memory` (`core/orchestrator.py`). The `market_session_memory_contract.install()` hook connects the OHLC buffer to the SQLite store, but repository search finds only the certification script calling `install()`. The normal runtime therefore does not establish that write-through/read-through bridge. In addition, `get_market_memory` only reads the store object's process-local `_bars_1m` list, not persisted rows, has no explicit symbol parameter, and C1/C2 currently does not pass `sym`. Its empty-store fallback fabricates default bar count/range/volatility/persistence values.

## Design contract

1. Reuse the existing `MarketSessionStore` SQLite authority and `market_session_memory_contract`; do not add another store or migrate evidence.
2. Configure the global OHLC buffer once at the explicit production market-data/orchestrator startup boundary, before any market-data update or C1/C2 evaluation. Importing modules alone must not write bars or silently configure authority.
3. The `core/market_data.py` ingestion boundary validates the source LTP timestamp before calling `OhlcBuffer.update_tick`. Accept only known `live`/`tick_store` sources with a finite, positive, present, non-future provider event timestamp belonging to that exact LTP observation; enforce the existing configured LTP age limit in market and off-hours sessions. Never substitute receipt/cycle time or a previous LTP's timestamp for a missing provider event timestamp, and never use cycle observation time as the bar timestamp. Book/depth timestamps cannot refresh cached LTP provenance. Missing, stale, cached, fallback, replay, non-finite, non-positive, or otherwise untrusted observations cannot create/finalize a trusted bar. Do not change configured age thresholds.
4. Persist only complete 1-minute bars accepted by the OHLC buffer, with existing provenance restrictions and completion event-time cutoff. Recovered bars are history only; they do not prove current feed freshness, subscription, or execution eligibility.
5. C1/C2 memory reads take the normalized symbol explicitly, use only same-session persisted completed bars whose completion time is `<= as_of`, and reject empty, corrupt, cross-session, or mismatched identity results. No cross-symbol reuse.
6. Remove fabricated defaults (bar count, volatility, range, persistence, session open). Missing memory remains not-ready and emits no candidate. Do not alter C1/C2 thresholds, windows, or predicates.
7. Freshness remains governed by existing live market-data/feed gates and additionally requires current row validity, `time_sanity.ok`, and a trusted `ltp_source` (`live` or `tick_store`). A restored historical bar cannot set a fresh-feed watermark. Missing or stale current proof makes memory stale/not-ready.
8. Current instrument-universe configuration, feed health truth, risk, kill switches, strategy contracts, and order/broker boundaries are immutable in this patch.

## Authorized scope

`core/market_data.py` (trusted source-time gate only), `core/market_session_memory_contract.py`, `core/market_session_store.py`, `core/orchestrator.py`, focused tests for these modules and C1/C2 integration, plus Issues 7–11 evidence artifacts. Runtime wiring is explicitly limited to the completed-bar persistence bridge required by Issue 9. No changes to launcher, broker, order, risk, feed producer/recovery internals, credentials, strategy thresholds, or instrument configuration.

## Acceptance gates

- Normal runtime startup installs/configures the bridge exactly once before buffer updates; disabled/unavailable persistence is explicit and cannot masquerade as persistence success.
- A stale quote crossing a minute boundary cannot finalize or persist a trusted live bar in market or off-hours sessions; apply the corresponding existing configured LTP age bound in both. Accepted updates use the source event timestamp, not cycle time; missing/future event timestamps and untrusted source labels cannot create trusted durable rows. No receive-time substitution may convert a missing provider event time into a trusted source time, and non-finite/non-positive prices cannot enter OHLC.
- A live-provenance completed bar written through the ordinary configured buffer is readable after constructing a fresh store instance; incomplete bars are absent before their completion cutoff.
- Symbol and session isolation hold for NIFTY/BANKNIFTY and across dates.
- C1/C2 receives only same-symbol causal persisted history; freshness requires explicit current validity, time-sanity, and trusted source; history cannot make a stale current feed fresh.
- Empty, corrupt, or mismatched stores produce not-ready/no candidate, never fabricated memory.
- Existing evaluator predicates, thresholds, windows, and candidate payload contracts remain unchanged.
- Adversarial tests cover wrong symbol, wrong date, incomplete current bar, corrupted timestamp/hash, disabled store, and absent freshness.
- Full relevant focused tests, broad regression with exclusions enumerated, source-hash registry validation, and independent code review pass.

**Hermes verdict:** scoped implementation approved. Historical persistence may supply causal history; it does not grant live, paper, broker, or order authority. Captured-session parity remains a separate evidence gate.

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
