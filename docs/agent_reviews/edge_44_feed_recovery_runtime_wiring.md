# Agent Review Evidence — EDGE-44 Feed Recovery Runtime Wiring

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

Answer: No. That is intentional. This PR adds deterministic recovery classification only. It avoids changing runtime behavior before the classification contract is proven.

Question: Can this place or alter trades?

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

The smallest useful increment is a pure classifier plus tests. Runtime JSON attachment and active recovery behavior can be separate PRs after the decision contract is stable.

## Scope Guard

No unrelated files are touched. No recovery execution is wired in this PR.

## Approval Evidence

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_recovery_runtime.py
```

Expected:

- Classifier handles healthy, closed, auth-blocked, disconnected, silent, missing subscription, option-blocked, and invalid payload cases.
