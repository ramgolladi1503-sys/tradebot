# Agent Review Evidence — EDGE-44 Feed Recovery Runtime Wiring

mode: PAPER
candidate_id: EDGE-44-FEED-RECOVERY-RUNTIME-WIRING
decision: APPROVED_FOR_CI_REVIEW
reason: Pure feed recovery runtime classification contract.
timestamp: 2026-05-23T19:58:47Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_44_feed_recovery_runtime_wiring.md

## Agent Work Contract

PR scope is limited to a pure runtime classifier for feed recovery states.

Allowed files:

- `core/feed_recovery_runtime.py`
- `tests/test_feed_recovery_runtime.py`
- `docs/EDGE_44_FEED_RECOVERY_RUNTIME_WIRING.md`
- `docs/agent_reviews/edge_44_feed_recovery_runtime_wiring.md`

Not allowed:

- Websocket restart behavior changes
- Broker integration changes
- Order/execution changes
- Strategy changes
- Dashboard changes
- Threshold changes

## Grill Me Review

Question: Does this actually recover the feed?

Answer: No. This PR adds deterministic recovery classification only.

Question: Can this alter trades?

Answer: No. The classifier is pure and imports no execution/order modules.

Question: Can this hide feed failures?

Answer: No. Unknown degraded states remain `DEGRADED_UNKNOWN` with `should_attempt_recovery=False` and `inspect_feed_runtime` action hint.

## Hermes Review

The classifier provides stable vocabulary for future runtime evidence:

- `recovery_state`
- `action_hint`
- `reason`
- `should_attempt_recovery`
- `force_full_restart`
- `context`

The payload is serializable and deterministic.

## GSD Review

The smallest useful increment is a pure classifier plus tests. Runtime JSON attachment can be a separate PR after the decision contract is stable.

## Scope Guard

No unrelated files are touched. No recovery execution is wired in this PR.

## QA / Safety Review

- The classifier is a pure function and only reads an input payload.
- Closed-market and auth-blocked states do not request recovery.
- Disconnected and silent-feed states are only expressed as action hints.
- The output remains evidence, not an action command.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_recovery_runtime.py
```

Expected proof:

- Healthy feed produces `HEALTHY` and no recovery request.
- Market closed produces `MARKET_CLOSED` and no recovery request.
- Auth blocked produces `AUTH_BLOCKED` and manual-auth hint.
- Disconnected websocket produces `WS_DISCONNECTED` and full-restart candidate hint.
- Silent feed produces `SILENT_FEED` and reconnect candidate hint.
- Missing option subscriptions produce `OPTION_SUBSCRIPTIONS_MISSING`.
- Option blocker evidence is preserved in `reason` and `context`.
- Invalid payload fails closed to `UNKNOWN`.

## Runtime Proof Required After Merge

A later wiring PR must prove:

- `feed_recovery.recovery_state` appears in runtime evidence.
- `feed_recovery.should_attempt_recovery` is visible for unhealthy feed states.
- Existing recovery behavior remains unchanged unless explicitly scoped.
- Recovery hints remain evidence only.

## What This PR Does Not Prove

- It does not prove reconnect success.
- It does not prove option subscriptions are repaired live.
- It does not prove dashboard display integration.
- It does not prove runtime JSON attachment.
- It does not change trading behavior.

## Human Approval

Approved to proceed as a small, read-only contract PR because it adds deterministic recovery-state evidence without changing runtime behavior.

## Approval Evidence

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_recovery_runtime.py
```

Expected:

- Classifier handles healthy, closed, auth-blocked, disconnected, silent, missing subscription, option-blocked, and invalid payload cases.


## High-Risk Path Review

N/A
