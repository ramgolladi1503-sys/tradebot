# LIVE-TRUTH-04 Feed Runtime Writer Liveness Agent Review

mode: REVIEW
candidate_id: live_truth_04_feed_runtime_writer_liveness
decision: review_ready
reason: writer_liveness_tests_docs
timestamp: 2026-05-27T11:15:00Z
source: live_truth_04_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

LIVE-TRUTH-04 adds read-only evidence for feed runtime writer liveness and WebSocket/subscription recovery visibility.

It proves whether the feed runtime writer is alive, stale, missing heartbeat evidence, or missing recovery visibility after known failure signals.

## Scope

In scope:

- Evaluate writer heartbeat freshness.
- Detect stale writer heartbeat evidence.
- Detect missing writer heartbeat evidence.
- Detect future writer heartbeat evidence.
- Detect WebSocket disconnect evidence without recovery visibility.
- Detect subscription failure evidence without recovery visibility.
- Preserve subscribed token counts in evidence.
- Optionally write read-only liveness evidence.

Out of scope:

- UI changes.
- Strategy changes.
- Feed recovery changes.
- Runtime loop wiring.
- Market-close behavior.
- Candidate generation.
- Strategy scoring.

## Scope Guard

- No dashboard work.
- No scoring work.
- No candidate generation work.
- No feed reconnect work.
- No resubscribe behavior.
- No market-close logic.
- No later LIVE-TRUTH items.
- No executable-quality gate change.

## Grill Me Review

Question: Does this PR reconnect WebSockets?

Answer: No. It only reports recovery visibility evidence.

Question: Does this PR resubscribe tokens?

Answer: No. It only reports writer and subscription recovery evidence.

Question: Can stale feed runtime writer evidence be reported as healthy?

Answer: No. The heartbeat must be present and within max age.

Question: Does this PR solve market-close quiescence?

Answer: No. That is LIVE-TRUTH-05.

Question: Does this PR change candidate generation or scoring?

Answer: No.

## Hermes Review

Boundary check:

- No external integration added.
- No UI change added.
- No strategy behavior changed.
- No candidate scoring changed.
- No feed reconnect behavior changed.
- Non-action metadata remains explicit in review evidence.

Verdict: scoped as feed runtime writer liveness and recovery visibility evidence only.

## GSD Review

Files changed are narrow:

- `core/live_truth_feed_runtime_writer_liveness.py`
- `tests/test_live_truth_04_feed_runtime_writer_liveness.py`
- `docs/LIVE_TRUTH_04_FEED_RUNTIME_WRITER_LIVENESS.md`
- `docs/agent_reviews/LIVE_TRUTH_04_FEED_RUNTIME_WRITER_LIVENESS.md`
- `docs/EDGE_TODO.md`

## QA / Safety Review

Tests cover:

- writer alive
- writer stale
- missing heartbeat
- invalid snapshot
- future heartbeat
- WebSocket recovery missing
- WebSocket recovery visible
- subscription recovery missing
- ISO timestamp parsing
- invalid config
- evidence file writing
- JSON serialization
- read-only/no-append metadata

## Acceptance Proof

Command:

`PYTHONPATH=. python -m pytest tests/test_live_truth_04_feed_runtime_writer_liveness.py`

Expected result:

- focused LIVE-TRUTH-04 tests pass
- writer heartbeat liveness is proven
- WebSocket recovery visibility is proven
- subscription recovery visibility is proven
- invalid and missing inputs block safely
- read-only/no-append flags remain explicit

## Runtime Proof Required After Merge

After merge, LIVE-TRUTH-04 proves only the writer liveness and recovery visibility reducer.

Runtime wiring must be added only if a later scoped PR explicitly requires it.

## What This PR Does Not Prove

This PR does not prove:

- actual WebSocket reconnect behavior
- actual token resubscribe behavior
- market-close quiescence
- stale candidate hygiene
- dashboard correctness
- pilot readiness

## Human Approval

Human review is required before wiring this utility into broader runtime loops.

## Next Action

After this PR merges green, continue with LIVE-TRUTH-05 — Market Close State Consistency / Off-Hours Quiescence.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
