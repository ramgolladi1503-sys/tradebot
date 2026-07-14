# Agent Review Evidence — PR-FEED-04 Feed Recovery Warmup Gate

## Agent Work Contract

### Goal

Add a read-only feed recovery warmup gate that prevents executable ranking output from resuming immediately after a feed recovery transition until explicit warmup evidence is satisfied.

### Files changed

- `core/feed_recovery_warmup_gate.py`
- `tests/test_pr_feed_04_feed_recovery_warmup_gate.py`
- `docs/PR_FEED_04_FEED_RECOVERY_WARMUP_GATE.md`
- `docs/agent_reviews/pr_feed_04_feed_recovery_warmup_gate.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_04_FEED_RECOVERY_WARMUP_GATE
decision: READ_ONLY_FEED_RECOVERY_WARMUP_GATE
reason: Feed recovery warmup blocks executable ranking output until elapsed-time and healthy-sample evidence is satisfied.
timestamp: 2026-05-24T19:52:14Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_04_feed_recovery_warmup_gate.md

### Non-goals

- No websocket refactor.
- No reconnect logic.
- No resubscribe logic.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No external execution API calls.
- No order intent.
- No live execution behavior.

## Grill Me Review

### Pushback

A healthy feed flag after recovery is not enough. If the bot resumes ranking immediately after a stale/down state flips healthy, it can still be operating on thin, unstable, or only partially recovered data.

### Required proof

- A recovered feed with insufficient elapsed warmup time must emit zero ranks.
- A recovered feed with too few healthy samples must emit zero ranks.
- Missing recovery timestamp during a recovery transition must fail closed.
- Completed warmup must preserve existing ranking behavior.

## Hermes Review

### Contract clarity

The gate consumes canonical `FeedHealthTruthDecision` plus explicit recovery metadata. It does not infer websocket lifecycle or mutate feed state.

### Serialization

The decision object provides `to_dict()` and `to_json()`. Serialized output includes `is_order_action=false` without direct mutable dataclass field assignment.

## GSD Review

### Determinism

Tests pass fixed `now_epoch` and `recovered_at_epoch` values to avoid fragile wall-clock behavior.

### Minimality

The PR adds one pure/read-only module and focused tests. It does not alter existing feed, ranking, strategy, or runtime wiring.

## QA / Safety Review

### Safety assertions

Tests assert:

- `read_only=True`
- `is_order_action=False`
- `append=False`
- `rank_count=0` while blocked
- `executable_count=0` while blocked
- no ranks while blocked

### Negative coverage

- Incomplete warmup elapsed time.
- Incomplete healthy sample count.
- Missing recovery timestamp.
- Unhealthy feed truth.

## Scope Guard

Confirmed not touched:

- Websocket lifecycle.
- Reconnect/resubscribe behavior.
- Token selection.
- Strategy code.
- Dashboard UI.
- External execution adapters.
- Live execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_03_feed_hold_gate.py tests/test_pr_feed_04_feed_recovery_warmup_gate.py
```

Expected:

- Feed hold behavior remains compatible.
- Feed recovery warmup behavior is proven.
- CI and repo gates green before merge.

## Runtime Proof Required After Merge

Before wiring this into runtime, capture real runtime evidence showing:

- previous feed unhealthy
- current feed healthy
- recovered timestamp
- healthy sample count
- elapsed warmup duration

This PR only defines the read-only contract. It does not claim runtime wiring exists.

## What This PR Does Not Prove

- It does not prove websocket reconnect quality.
- It does not prove subscription recovery.
- It does not prove token freshness.
- It does not prove strategy edge.
- It does not prove live readiness.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only feed recovery warmup gating.


## High-Risk Path Review

N/A
