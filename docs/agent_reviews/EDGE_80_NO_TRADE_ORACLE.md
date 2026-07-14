# EDGE-80 NoTradeOracle Agent Review

mode: REVIEW
candidate_id: edge_80_no_trade_oracle
decision: review_ready
reason: no_trade_oracle_contract_tests_docs
timestamp: 2026-05-26T14:20:00Z
source: edge80_no_trade_oracle_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

EDGE-80 adds the canonical NoTradeOracle explanation layer.

The report explains why the bot should not trade by consuming already computed evidence from feed truth, feed hold, market-close feed state, indicator readiness, opportunity scoring, candidate ranking, and executable truth.

## Work contract

This PR covers explanation only.

It does not place orders, create order intent, wire runtime, change dashboard, reconnect feeds, resubscribe tokens, compute indicators, score opportunities, or rank candidates.

## Scope guard

- Missing evidence fails closed.
- Feed health problems are explained separately from feed hold.
- Market closed and close-feed states preserve their classifier state.
- Indicator readiness preserves per-symbol blockers.
- Scoring and ranking evidence explain when no eligible/executable candidates exist.
- Executable-truth evidence explains when every supplied candidate is blocked.
- Output remains read-only, no-append, and non-action.

## High-risk path review

The high-risk path is turning NoTradeOracle into another filter or hidden action gate.

Controls:

- The oracle only builds a report.
- The oracle accepts already computed evidence and does not recompute strategy edge.
- Clean evidence returns `TRADE_ALLOWED_BY_SUPPLIED_EVIDENCE`, but still marks the payload as non-action.
- Missing evidence returns `NO_TRADE_REQUIRED`.
- No dashboard or runtime wiring exists in this PR.

## Grill Me Review

Question: Can this PR place or modify a trade?

Answer: No. There is no execution adapter import, no runtime writer, and no order lifecycle mutation. Payloads expose non-action markers.

Question: Can this PR hide feed problems behind generic candidate failure?

Answer: No. Feed health, feed hold, and market-close feed state produce separate reason codes and evidence payloads.

Question: Can this PR fake safety by allowing trade when no evidence is available?

Answer: No. Missing evidence fails closed with `missing_no_trade_evidence`.

Question: Does this PR display anything in the UI?

Answer: No. EDGE-81 is responsible for review queue/UI surfacing.

## Hermes Review

Public contract:

- `build_no_trade_oracle_report(...)`
- `NoTradeOracleReport.to_payload()`
- `NoTradeReason.to_dict()`
- canonical reason constants

The contract is stable enough for EDGE-81 to consume without changing runtime behavior.

## GSD Review

The PR is narrow:

- one core oracle module
- one focused test file
- one implementation doc
- one agent-review evidence file
- TODO update

No unrelated refactor is included.

## QA / safety review

Focused tests cover:

- missing evidence fail-closed behavior
- feed health and feed hold blockers
- market closed priority
- indicator readiness blockers
- zero scored candidates
- no score-eligible candidates
- no executable ranked candidates
- executable-truth blocked candidates
- clean evidence report with non-action markers

## Runtime Proof Required After Merge

After merge, EDGE-81 can surface the report in review queue/UI.

Any future runtime wiring must remain read-only unless a later PR explicitly scopes a gate with separate tests and human review.

## What This PR Does Not Prove

This PR does not prove live profitability, final executable quality, paper expectancy, strategy lifecycle quality, feed recovery, or UI usability.

Those belong to later roadmap items.

## Required Check Context Reconciliation

The pull-request test context passed after the EDGE-80 evidence payload fix.

A required push-context check showed an older torture replay failure for `test_torture_replay_feed_flap_partial_data` while the pull-request context later completed the full suite successfully.

This note intentionally changes no runtime, product, oracle, strategy, dashboard, feed, broker, or test behavior. It exists only to create a fresh branch SHA so GitHub evaluates the required push-context check again before merge.

If the fresh required push check repeats the same torture replay failure, the next action is a scoped torture replay stability fix with evidence, not an EDGE-80 oracle change.

## Human Approval

Human review is required before any later PR uses this oracle to change execution behavior.

## Acceptance proof

Command:

`PYTHONPATH=. python -m pytest tests/test_edge_80_no_trade_oracle.py`

Expected result:

- focused EDGE-80 tests pass
- missing evidence fails closed
- no-trade reasons are deterministic
- clean supplied evidence remains non-action


## Scope Guard

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A
