# PR #763 Offline Persistence Certification

This evidence was generated offline. No broker, Kite WebSocket, live market process, or order authority was started.

- Implementation SHA: `eda4a92561c903b2c60eafab75d4b4b61b578063`
- Verdict: `REAL_CALLBACK_PERSISTENCE_GATE_CLOSED`
- Generated at: `2026-08-03T14:33:16.625187+00:00`
- Registered callback: `_register_on_ticks_callback -> kws.on_ticks -> core.kite_depth_ws.on_ticks`
- Live started: `false`

## Callback and worker ownership

- Callback: `MainThread` / `139900093975424`
- Tick worker: `tick-store-flush` / `139899548198592`
- Depth worker: `depth-store-persistence` / `139899581757120`
- Runtime worker: `feed-runtime-persistence` / `139899531417280`
- Wrapper entries/exits: `1 / 1`
- Delegate entries/exits: `1 / 1`
- Callback exceptions: `0`
- Maximum callback duration: `2.125261 ms`
- Frozen callback SLA: `5000.000 ms`

## Authority reconciliation

| Authority | Accepted | Persisted | Pending | Rejected | Failures | Drain |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tick | 2 | 2 | 0 | 0 | 0 | complete |
| depth | 1 | 1 | 0 | 0 | 0 | complete |
| runtime | 1 | 1 | 0 | 0 | 0 | complete |

## Callback-boundary tripwires

- SQLite normal violations: `0`
- Synchronous-store normal violations: `0`
- Scoped-filesystem normal violations: `0`
- SQLite operation controls passing: `8` / `8`
- Synchronous-store controls passing: `4` / `4`
- Scoped-open controls passing: `2` / `2`
- Unscoped open falsely classified: `false`

## Launcher-derived state

- constituent: configured=`true`, effective=`false`, traversals=`0`, consumer=`launch plan / constituent source`, disabled_reason=`NOT_APPLICABLE_TO_GATE1_PERSISTENCE_FIXTURE`
- live_source: configured=`true`, effective=`true`, traversals=`0`, consumer=`core.kite_depth_ws launch-plan activation`, disabled_reason=`None`
- meg: configured=`true`, effective=`false`, traversals=`0`, consumer=`market-event-graph runtime bridge`, disabled_reason=`NOT_APPLICABLE_TO_GATE1_PERSISTENCE_FIXTURE`
- observer: configured=`true`, effective=`true`, traversals=`1`, consumer=`runtime_observer.enabled/from_env`, disabled_reason=`None`

## Validation

- focused_gate1: returncode=`0`, summary=`43 passed in 52.48s`
- gate1a: returncode=`0`, summary=`2 passed, 38 deselected in 0.22s`
- gate6: returncode=`0`, summary=`7 passed, 33 deselected in 0.21s`
- callback_regressions: returncode=`0`, summary=`41 passed in 0.39s`
- compilation: returncode=`0`, summary=`no stdout`

## Missing controls

- None

## Safety

`TRADEBOT_READ_ONLY=true` remained mandatory. The certification started no broker API, WebSocket, order action, or live market process.
