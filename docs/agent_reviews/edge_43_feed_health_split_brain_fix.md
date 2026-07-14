# Agent Review Evidence — EDGE-43 Feed Health Split-Brain Fix

mode: PAPER
candidate_id: EDGE-43-FEED-HEALTH-SPLIT-BRAIN-FIX
decision: APPROVED_FOR_CI_REVIEW
reason: Read-only feed health truth contract only.
timestamp: 2026-05-23T22:18:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_43_feed_health_split_brain_fix.md

## Agent Work Contract

Scope is limited to canonical feed-health truth classification for runtime diagnostic evidence.

Allowed files:

- `core/feed_health_truth.py`
- `tests/test_edge43_feed_health_truth.py`
- `docs/EDGE_43_FEED_HEALTH_SPLIT_BRAIN_FIX.md`
- `docs/agent_reviews/edge_43_feed_health_split_brain_fix.md`

Not allowed:

- Broker calls
- Websocket reconnects
- Subscription mutation
- Runtime mutation
- Strategy tuning
- Dashboard changes
- Threshold loosening
- Order behavior

## Grill Me Review

Question: Does this reconnect the feed?

Answer: No. It only classifies feed truth so split-brain evidence can be identified deterministically.

Question: Does this prove feed recovery is working?

Answer: No. Recovery hints remain separate. This PR only reconciles global and symbol-level health evidence.

Question: Can a symbol still look healthy while global feed is unhealthy?

Answer: The symbol evidence can remain individually healthy for audit clarity, but the top-level feed truth fails closed with `global_feed_unhealthy`.

## Hermes Review

The canonical feed-health payload exposes stable keys:

- `feed_ok`
- `reason_code`
- `reasons`
- `global_feed_ok`
- `websocket_ok`
- `symbols`
- `context`

Each symbol exposes:

- `symbol`
- `feed_ok`
- `reason_code`
- `reasons`
- `option_feed_block_reason`
- `option_last_tick_age_sec`
- `context`

The payload is deterministic and serializable.

## GSD Review

The smallest useful increment is a pure classifier that reconciles global feed and per-symbol option feed evidence. This avoids touching runtime recovery or dashboard code before the truth contract exists.

## Scope Guard

No unrelated files are touched. No runtime feed behavior changes. No thresholds are loosened to hide stale data.

## QA / Safety Review

- Invalid payload fails closed.
- Global unhealthy feed blocks top-level truth.
- Disconnected websocket blocks top-level truth.
- Stale option tick age blocks symbol and top-level truth.
- Non-OK option feed blocker is preserved.
- No broker or websocket imports are introduced.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge43_feed_health_truth.py
```

Expected proof:

- Healthy global and symbol feed passes.
- Global unhealthy feed blocks even when per-symbol reason is `OK`.
- Websocket disconnected blocks.
- Symbol stale option tick age blocks.
- Option-feed blocker is preserved.
- Invalid payload fails closed.

## Runtime Proof Required After Merge

Later PRs must prove runtime evidence and reporting consume this canonical feed truth instead of reading mixed raw fields directly.

## What This PR Does Not Prove

- It does not reconnect the feed.
- It does not fix broker subscriptions.
- It does not alter strategy behavior.
- It does not prove profitability.
- It does not wire dashboard output.

## Human Approval

Approved to proceed as a small feed-truth contract PR because it addresses split-brain feed evidence without changing runtime behavior.

## Approval Evidence

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge43_feed_health_truth.py
```


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
