# PR #763 Offline Persistence Certification

This is an offline certification record. No broker, Kite, live WebSocket, or
market-session process was started.

| Gate | Tests | Result | Measured values | Remaining defect |
| --- | --- | --- | --- | --- |
| 1. Real callback tripwire | `test_callback_reachable_sources_have_no_direct_persistence_calls` | PARTIAL | 0 direct forbidden calls in `on_ticks` AST | Full registered-hook runtime tripwire not implemented |
| 2. Static guard | `test_static_guard_detects_injected_forbidden_call` | PASS | Injected `sqlite3.connect` detected | Guard scope remains narrow |
| 3. Envelopes/sequences | `test_runtime_envelope_is_deeply_immutable` | PARTIAL | Runtime nested mutation blocked | Tick/depth sequence envelopes not proven |
| 4. Worker ownership | `test_runtime_worker_is_not_simulated_reactor_thread` | PARTIAL | Worker thread differs from reactor | Connection/filesystem ownership matrix absent |
| 5. Slow-store matrix | focused worker tests | PARTIAL | Depth/runtime enqueue behavior tested | Full real-callback matrix and drift measurements absent |
| 6. Saturation/durability | Gate-6 tests in `test_pr763_callback_persistence_cutover_certification.py` | PASS | 20 dedicated certification tests; bounded `put_nowait`; aggregate degradation and execution fail-closed checks pass | Per-envelope production counters remain authority-local |
| 7. Read-after-write/restart | semantics document | PARTIAL | In-memory source documented | Required restart reconstruction tests absent |
| 8. Shutdown/post-seal | focused drain tests | PARTIAL | Normal depth/runtime drain covered | Timeout and post-seal evidence mutation proof absent |

## Gate 1A: registered wrapper traversal

Status: `GATE_1A_REGISTERED_WRAPPER_TRAVERSAL_PASS`

- Actual wrapper: `core.kite_depth_ws._register_on_ticks_callback` returned callback, installed as `kws.on_ticks`; production registration uses this helper.
- Delegate: `core.kite_depth_ws.on_ticks`
- Registration site: `core/kite_depth_ws.py:8412` (startup path)
- Traversal: wrapper entry/exit `1/1`, delegate entry/exit `1/1`, diagnostic stage marker count positive, callback exception none.
- Callback duration: below the 5-second offline bound.
- Enabled hooks: raw truth and diagnostic stage markers, both traversed.
- Explicitly disabled by frozen configuration: tick/depth/runtime enqueue, observation, constituent, MEG, and candidate/ranking hooks in this fixture, each recorded as `NOT_ENABLED_BY_FROZEN_CONFIGURATION`.
- Negative control: missing enabled hook is reported by exact hook name.
- Worker drain: not part of the Gate 1A wrapper-only fixture; Gate 6 worker tests remain separate.

## Gate 1B: live-shaped registered callback persistence tripwire

Status: `REAL_CALLBACK_PERSISTENCE_GATE_FAILED`

- Registered wrapper: `core/kite_depth_ws._register_on_ticks_callback` installed as `kws.on_ticks`; delegate was the real `core.kite_depth_ws.on_ticks`.
- Mandatory live-shaped enqueue traversal: tick `>=1`, depth `>=1`, runtime `>=1`, diagnostic markers `>=1`.
- First defect repaired: `tick_store._enqueue_row` called `init_ticks()` on the callback thread. Schema initialization now remains in worker-owned `_write_rows`.
- Callback-thread tripwire result: SQLite `0`, persistent-store `0`, scoped filesystem `0`.
- Runtime negative controls: injected SQLite, store, and filesystem calls were each detected with category and target.
- Worker allowance: accepted tick/depth/runtime work drained through the existing bounded workers; worker calls were not classified as callback violations.
- Callback entries/exits: `1/1`; callback exceptions: `0`; duration: below 5 seconds.
- Optional observation/constituent/MEG/candidate hooks remain governed by their existing campaign configuration and were not enabled by this fixture.

## Final Gate 1 closure evidence

The registered live-shaped fixture now trips the mandatory tick, depth, and
runtime enqueue boundaries while wrapping synchronous repository targets:
`tick_store._conn`, `tick_store._write_rows`, `tick_store.init_ticks`,
`trade_store._conn`, `trade_store.insert_depth_snapshot`,
`runtime_store._conn`, `runtime_store._write_runtime_snapshot_sync`, and
`events.write_json_atomic`. Callback-thread violations were zero. Runtime
negative controls detected injected tick, depth, runtime, event, SQLite, and
scoped filesystem operations. The fixture explicitly checks the launcher
source sets `UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE` and
`MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE` to true; optional observer details
remain configuration-governed.

The previous closure claim is withdrawn. The dedicated module passed its
existing tests, but those tests do not retain exact machine-readable worker
identities, per-authority accepted/persisted deltas, numeric callback timing,
or executed launcher effective hook state. They also do not provide dedicated
tick/runtime/event negative controls, SQLite operation-level proxy coverage,
or scoped `builtins.open`/`Path.open` coverage.

Machine-readable evidence: `docs/pr763_gate1_evidence_20260803.json`.

Gate 1 remains blocked until every missing control listed in that artifact is
implemented and independently passing.

Cutover unresolved count for certification: non-zero. The implementation has
bounded worker routing, but this record does not claim live readiness.

## Gate 6 results

| authority | capacity | saturation result | degradation |
| --- | ---: | --- | --- |
| tick | 1 in test | rejection is bounded and recorded | aggregate degraded; execution false |
| depth | 1 in test | rejection is bounded and recorded | aggregate degraded; execution false |
| runtime | 1 in test | rejection is bounded and recorded | aggregate degraded; execution false |
| combined | 1 per authority in fixture | no callback deadlock | `degraded_authorities` is deterministic and deduplicated |

## Safety

`TRADEBOT_READ_ONLY=true` was preserved. No broker API, order action,
execution enablement, feed/MEG/strategy/risk/subscription change, or evidence
mutation was performed.
