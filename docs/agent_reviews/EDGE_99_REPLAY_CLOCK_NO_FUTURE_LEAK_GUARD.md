# EDGE-99 — Replay Clock and No-Future-Leak Guard — Agent Review Evidence

## Agent Work Contract

- mode: REVIEW_ONLY
- candidate_id: EDGE-99
- decision: PASS
- reason: Replay-time authority added with deterministic no-future access checks, monotonic advancement, lookback enforcement, and read-only evidence payloads.
- timestamp: 2026-05-28T10:45:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: agent_review_edge_99_replay_clock_no_future_leak_guard

## Scope Guard

This PR is limited to the EDGE-99 card:

- Add `core/backtest_replay_clock.py`.
- Add `tests/test_edge_99_replay_clock_no_future_leak.py`.
- Add this agent-review evidence file.
- Add `docs/EDGE_99_REPLAY_CLOCK_NO_FUTURE_LEAK_GUARD.md`.
- Update `docs/EDGE_TODO.md` so issue #320 is removed from remaining work.

No broker adapter, live execution, strategy execution, candidate runner, ranking, feed adapter, metrics, paper journal, or dashboard/UI path is changed.

## Grill Me Review

The main risk is future-data leakage during replay. The implementation blocks that through a replay-time authority rather than relying on caller discipline.

Checked behavior:

- Clock starts at configured session start.
- Clock movement cannot go backward.
- Current timestamp cannot leave the configured session.
- Snapshot timestamps later than current replay time return `BLOCK`.
- Same-timestamp access returns `ALLOW`.
- Past snapshots outside configured lookback return `BLOCK`.
- Candle derived fields requiring full candle visibility are blocked before candle end.
- Full-session aggregates are blocked before session completion.
- Non-monotonic replay timestamp sequences raise a contract error.

## Hermes Review

The contract is deterministic and JSON-friendly:

- `ReplayAccessDecision.to_payload()` emits stable fields.
- Decision payloads include explicit read-only and non-action markers.
- Timestamps are normalized to UTC ISO-8601 `Z`.
- Decisions expose clear reason codes for future consumers.

No external services, broker clients, network calls, runtime writers, or append behavior are introduced.

## GSD Review

This change improves backtest truth by preventing replay consumers from accidentally seeing unavailable future data. It is intentionally small and foundation-only. It does not attempt to run strategies or compute expectancy.

Acceptance proof is test-driven and focused on the issue #320 contract.

## QA / Safety Review

Focused test command:

```bash
pytest tests/test_edge_99_replay_clock_no_future_leak.py -q
# 9 passed
```

Safety properties covered:

- No future snapshot access.
- No backward clock movement.
- No future high/low/close access before candle completion.
- No full-session aggregate access before session completion.
- No non-monotonic replay timeline acceptance.
- Payload remains read-only and non-action.

## Acceptance Proof

Issue #320 acceptance criteria mapping:

- Replay clock starts from configured session timestamp: covered.
- Clock advances monotonically: covered.
- Access to snapshots after current timestamp is blocked: covered.
- Same-timestamp access is allowed: covered.
- Past snapshots are allowed only within configured lookback policy: covered.
- Future candle high/low/close access is rejected: covered.
- Full-session aggregates are unavailable before session completion: covered.
- Invalid non-monotonic replay data fails closed: covered.
- Tests prove no future data can be accessed: covered.

## Runtime Proof Required After Merge

None for this PR. EDGE-99 is a pure read-only replay contract and does not wire into live runtime, broker access, dashboard, paper journal, or strategy execution.

## What This PR Does Not Prove

This PR does not prove replay profitability, strategy quality, ranking quality, candidate execution quality, or walk-forward edge. It only proves that the replay clock contract can block future data access when used by future replay layers.

## Human Approval

Human review is required before merge. This PR should not be treated as permission to wire replay execution, broker behavior, dashboard changes, or candidate ranking.

## High-Risk Path Review

High-risk path touched:

- `core/backtest_replay_clock.py`

Risk control:

- Pure Python contract only.
- No external calls.
- No broker imports.
- No execution side effects.
- Strict timezone/session validation.
- Deterministic tests cover no-future leakage.
