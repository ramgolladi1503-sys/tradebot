# LIVE-TRUTH-05 Market Close State Consistency Agent Review

mode: REVIEW
candidate_id: live_truth_05_market_close_state_consistency
decision: review_ready
reason: market_close_consistency_tests_docs
timestamp: 2026-05-27T11:40:00Z
source: live_truth_05_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

LIVE-TRUTH-05 adds read-only evidence for market-close state consistency and off-hours quiescence.

It proves whether close-state artifacts agree that the market is closed/off-hours, whether candidate and executable counts are quiet, and whether runtime health has stopped high-frequency loop behavior.

## Scope

In scope:

- Validate market close from `market_snapshot.market_open=false`.
- Detect feed-runtime market-open conflicts without freshness warning.
- Require top opportunities to report closed/off-hours state.
- Require candidate counts to be quiet unless off-hours planning is explicit.
- Require executable count to be zero after close.
- Require runtime health to show quiet/off-hours mode.
- Detect high-frequency loop activity after close.
- Optionally write read-only consistency evidence.

Out of scope:

- UI changes.
- Strategy changes.
- Feed recovery changes.
- Runtime loop wiring.
- Scheduler changes.
- Candidate generation.
- Strategy scoring.

## Scope Guard

- No dashboard work.
- No scoring work.
- No candidate generation work.
- No feed reconnect work.
- No resubscribe behavior.
- No runtime loop mutation.
- No later LIVE-TRUTH items.
- No executable-quality gate change.

## Grill Me Review

Question: Does this PR stop runtime loops after close?

Answer: No. It only proves whether loop evidence is quiet or still active.

Question: Does this PR mutate market state?

Answer: No. It only evaluates provided artifacts.

Question: Can top opportunities still show normal NO_TRADE after close?

Answer: The reducer flags that as inconsistent because close evidence must be explicit.

Question: Can candidates exist after close?

Answer: Only if off-hours planning/replay analysis is explicitly enabled. Otherwise it is flagged as inconsistent.

Question: Does this PR solve stale candidate hygiene?

Answer: No. That is LIVE-TRUTH-06.

## Hermes Review

Boundary check:

- No external integration added.
- No UI change added.
- No strategy behavior changed.
- No candidate scoring changed.
- No feed reconnect behavior changed.
- Non-action metadata remains explicit in review evidence.

Verdict: scoped as market-close consistency evidence only.

## GSD Review

Files changed are narrow:

- `core/live_truth_market_close_state_consistency.py`
- `tests/test_live_truth_05_market_close_state_consistency.py`
- `docs/LIVE_TRUTH_05_MARKET_CLOSE_STATE_CONSISTENCY.md`
- `docs/agent_reviews/LIVE_TRUTH_05_MARKET_CLOSE_STATE_CONSISTENCY.md`
- `docs/EDGE_TODO.md`

## QA / Safety Review

Tests cover:

- consistent market-close evidence
- market-open not-applicable state
- invalid market snapshot blocking
- missing market-open blocking
- feed-runtime market-open conflict without freshness warning
- freshness warning allowance
- missing top-opportunities market state
- normal no-trade after close rejected
- source candidate count after close rejected unless off-hours planning is enabled
- executable count after close rejected
- runtime health not quiet rejected
- high-frequency loop activity rejected
- evidence file writing
- JSON serialization
- read-only/no-append metadata

## Acceptance Proof

Command:

`PYTHONPATH=. python -m pytest tests/test_live_truth_05_market_close_state_consistency.py`

Expected result:

- focused LIVE-TRUTH-05 tests pass
- close-state consistency is proven
- contradictory close-state artifacts are flagged
- non-quiet candidate/executable counts are flagged
- high-frequency loop activity is flagged
- read-only/no-append flags remain explicit

## Runtime Proof Required After Merge

After merge, LIVE-TRUTH-05 proves only the close-state consistency reducer and evidence writer.

Runtime wiring must be added only if a later scoped PR explicitly requires it.

## What This PR Does Not Prove

This PR does not prove:

- actual loop shutdown behavior
- stale candidate hygiene
- dashboard correctness
- strategy lifecycle readiness
- pilot readiness

## Human Approval

Human review is required before wiring this utility into broader runtime loops.

## Next Action

After this PR merges green, continue with LIVE-TRUTH-06 — Stale Candidate Hygiene Guard.


## High-Risk Path Review

N/A
