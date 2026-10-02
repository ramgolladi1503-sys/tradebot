# Hermes → GSD Contract: MEG Live Volume Capture

## Hermes architecture and acceptance gates

**source_agent:** hermes
**action:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**title:** Preserve cumulative-volume truth in the isolated MEG live-source observer
**scope:** Kite packet volume forwarding and volume semantics in the MEG shadow OHLC buffer only.
**requested_paths:** `core/kite_depth_ws.py`, `core/market_event_graph_live_ohlc_buffer.py`, `core/ohlc_buffer.py`, focused tests, this contract.
**allowed_paths:** The requested paths only.
**forbidden_paths:** Broker/order/risk/strategy/configuration paths, credentials, runtime process state, and live execution behavior.

### Invariants

- Kite packet volume is a cumulative daily counter. It must never be summed as if it were a per-tick quantity.
- The observer derives nonnegative deltas per instrument token and attributes each observed delta to the source tick's minute. Deltas spanning observation gaps are estimates, not authoritative exchange minute volume.
- Every derived OHLC volume bar carries `volume_is_estimate=true` and `volume_attribution=CURRENT_SOURCE_TICK_MINUTE_ESTIMATE`; completeness means a valid cumulative baseline and uninterrupted valid deltas within that bar, not exact exchange minute allocation.
- First observation after reset, feed/day identity change, cumulative regression, missing, or invalid volume is incomplete. The OHLC bar volume is `null` if any constituent observation made it incomplete; never substitute zero for unknown.
- Invalid or unavailable volume must not reject an otherwise valid price tick.
- This data remains in the isolated MEG shadow buffer and cannot feed strategies, risk, or execution.
- Existing `OhlcBuffer` callers that do not explicitly provide volume-quality metadata retain their current behavior.

### GSD execution and verification

**source_agent:** gsd
**action:** `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`
**expected_tests:** Baseline then delta and repeated-value behavior; bar incompleteness; new-bar complete delta behavior; regression rebaseline; price acceptance on invalid/missing volume; ordinary OhlcBuffer compatibility; packet forwarding at the websocket observer callsite.
**acceptance_proof:** Focused MEG and websocket observer tests pass; no changes to strategy/broker/order/risk paths; diff and repository status reviewed.

### Migration and operations

No configuration keys or data migration are introduced. Consumers of MEG shadow bars must treat `volume: null` as unavailable and inspect `bar_provenance.volume_observation_complete`, `volume_delta_status`, `volume_attribution`, and `volume_is_estimate`. Re-run the focused tests in CI before accepting the patch. This does not certify live readiness or exact per-minute volume.
