# Agent Review Evidence — PR-FEED-20 Feed Runtime Evidence Bundle

## Agent Work Contract

### Goal

Add a read-only feed runtime evidence bundle that packages policy decision, config audit, sanitized runtime feed snapshot, symbols, mode, and safety metadata into one deterministic evidence object.

### Files changed

- `core/feed_runtime_evidence.py`
- `tests/test_pr_feed_20_feed_runtime_evidence_bundle.py`
- `docs/PR_FEED_20_FEED_RUNTIME_EVIDENCE_BUNDLE.md`
- `docs/agent_reviews/pr_feed_20_feed_runtime_evidence_bundle.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_20_FEED_RUNTIME_EVIDENCE_BUNDLE
message_decision: READ_ONLY_FEED_RUNTIME_EVIDENCE_BUNDLE
decision: READ_ONLY_FEED_RUNTIME_EVIDENCE_BUNDLE
reason: Feed runtime evidence is now packaged into a deterministic read-only bundle with policy decision, config audit, and sanitized feed snapshot.
timestamp: 2026-05-25T10:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_20_feed_runtime_evidence_bundle.md

### Non-goals

- No runtime file writing.
- No dashboard wiring.
- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No ranking changes.
- No strategy changes.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

Feed safety decisions are not enough unless runtime can later emit one complete evidence bundle showing what policy, config, payload, mode, and symbols produced the decision.

### Required proof

- Bundle is read-only and non-action.
- Bundle embeds policy decision and config audit evidence.
- Bundle sanitizes runtime feed snapshot.
- Invalid runtime payload fails closed.
- Invalid config fails closed.
- SIM/BACKTEST remains explicitly SIM policy.

## Hermes Review

### Contract clarity

`FeedRuntimeEvidenceBundle` is a serialization-safe evidence contract. It does not write files or mutate runtime state.

### Safety boundary

The bundle emits `is_order_action=false` and `broker_api_called=false`. It does not import broker, websocket, order, ranking, or strategy modules.

## GSD Review

### Minimality

The PR adds only the evidence bundle seam. It does not wire runtime emission yet and does not alter live/paper behavior.

### Determinism

Bundle contents are deterministic over supplied payload, mode, symbols, and config except for `generated_epoch`.

## QA / Safety Review

Tests assert:

- Bundle remains read-only and non-action.
- Policy decision and config audit are embedded.
- Runtime snapshot only copies known feed-health fields.
- Unknown keys are visible only through `snapshot_keys`.
- Invalid runtime payload fails closed.
- Invalid config fails closed.
- JSON contains non-action evidence fields.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token resolution.
- Ranking behavior.
- Strategy code.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_20_feed_runtime_evidence_bundle.py tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Expected:

- feed runtime evidence bundle tests pass.
- feed config hardening tests remain green.
- feed policy tests remain green.

## Runtime Proof Required After Merge

Later runtime wiring must prove:

- Bundle is emitted once per scoped runtime cycle.
- LIVE/PAPER/SIM policy is visible in evidence.
- Invalid payload/config cannot emit healthy evidence.
- Evidence remains read-only and broker-free.
- No order action path consumes this bundle as permission to trade.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove token freshness.
- It does not write runtime artifacts yet.
- It does not prove strategy edge or profitability.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only feed runtime evidence bundling.


## High-Risk Path Review

N/A
