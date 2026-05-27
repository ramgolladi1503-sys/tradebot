# EDGE-88 — Strategy Lifecycle States

## Purpose

EDGE-88 adds a read-only, deterministic strategy lifecycle state model.

The model consumes EDGE-87 strategy-family `KEEP` / `WATCH` / `KILL` evidence and derives lifecycle state evidence that later PRs can use for promotion, suspension, and retirement gates.

This PR does **not** apply any lifecycle transition. It only produces evidence.

## Scope

Added:

- `core/strategy_lifecycle_states.py`
- `tests/test_edge_88_strategy_lifecycle_states.py`

## Input contract

The reducer accepts a strategy-family report payload with:

- `status == STRATEGY_FAMILY_REPORT_REDUCED`
- `read_only == true`
- `append == false`
- `recommendations` list

Each recommendation is expected to include family-level evidence such as:

- `strategy_family`
- `recommendation`
- `strategy_ids`
- `regimes`
- `closed_count`
- `net_expectancy_per_trade`
- `net_win_rate`
- `sample_ok`
- `reason_code`
- `reasons`

## Derived lifecycle states

The reducer emits one lifecycle state per strategy family:

| EDGE-87 recommendation | Evidence condition | EDGE-88 lifecycle state |
|---|---:|---|
| `KEEP` | sample OK | `ACTIVE_ELIGIBLE` |
| `WATCH` | sample OK | `WATCHLIST` |
| `KILL` | closed count below retire threshold | `SUSPEND_CANDIDATE` |
| `KILL` | closed count at/above retire threshold | `RETIRED_CANDIDATE` |
| any recommendation | sample not OK | `CANDIDATE` |
| unknown recommendation | fail-safe | `WATCHLIST` |

## Fail-closed behavior

The reducer blocks when:

- the family report is not reduced / read-only / append-false
- recommendations are missing
- lifecycle policy is invalid

Unknown recommendations do not become active. They are routed to `WATCHLIST` for review.

## Explicit non-goals

This PR does not:

- call broker APIs
- place, modify, cancel, or exit orders
- wire into live runtime
- alter dashboards/UI
- promote strategies
- suspend strategies
- retire strategies
- mutate strategy lifecycle state
- alter strategy scoring, ranking, or execution

## Evidence contract

Every report and state includes non-action markers:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false
}
```

Lifecycle outputs also explicitly keep action flags false:

- `promotion_applied == false`
- `suspension_applied == false`
- `retirement_applied == false`

## Acceptance proof

Focused tests cover:

- `KEEP` to `ACTIVE_ELIGIBLE`
- `WATCH` to `WATCHLIST`
- low-sample evidence to `CANDIDATE`
- `KILL` to `SUSPEND_CANDIDATE`
- `KILL` to `RETIRED_CANDIDATE`
- unknown recommendation fail-safe behavior
- invalid family report blocking
- empty recommendation blocking
- invalid policy blocking
- JSON serializability and non-action markers

Run:

```bash
pytest tests/test_edge_88_strategy_lifecycle_states.py
```
