# PR #763 NIFTY Post-Mode Full Failure - 2026-07-31

## Failed Run

- Run ID: `unified-pr748-756-20260731-76926b16c22f-live-d0df4c12`
- Campaign commit SHA: `79601ae0bf8f1eac6fba9ecc370d98a572cae079`
- Composition manifest SHA: `76926b16c22fd9daf9952c1741252ae4e13da82d797359d5919f0270749f6a57`
- Evidence root: `runtime/diagnostics/unified_live_validation_pr748_756_v1/unified-pr748-756-20260731-76926b16c22f-live-d0df4c12`
- Artifact manifest SHA: `c589500f865f8b5c7504f106abc818e6f0824760601241d2543cb285e94f7208`
- Sealed: true

Classification:

```text
POST_FIX_LIVE_DEFECT_OBSERVED
MISSING_POST_MODE_FULL_PAYLOAD
```

## NIFTY Lifecycle Observed

The sealed campaign observer subscription rows were present, but the PR #749 observer rows did not include bounded per-token packet diagnostics. The runtime stderr repeatedly emitted:

```text
market_event_graph_live_source_rejected reason=MISSING_POST_MODE_FULL_PAYLOAD identities=NIFTY
```

The run had advanced past the earlier `SUBSCRIPTION_REQUEST_FAILED` blocker. That means NIFTY subscription and mode-success evidence existed, but `first_full_payload_epoch` for NIFTY was not recorded after mode success.

## Installed Parser

- Installed Kite client version: `5.2.0`
- Parser file: `/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/site-packages/kiteconnect/ticker.py`

Parser findings:

- Index quote packet length: 28 bytes.
- Index quote parsed keys include `tradable`, `mode`, `instrument_token`, `last_price`, `ohlc`, `change`.
- Index full packet length: 32 bytes.
- Index full parsed keys include the quote keys plus `exchange_timestamp`.
- Reliable primary discriminator: `tick["mode"] == "full"`.
- Reliable fallback discriminator for index packets: non-null `exchange_timestamp`, because the installed parser only attaches it for 32-byte index full packets.

## Root Cause

Case A applies:

```text
Actual full index packet semantics were not correctly represented by the recorder.
```

The old recorder classified NIFTY full payloads with:

```text
ohlc present and change present
```

That is wrong for Kite index packets because both quote and full index packets have OHLC and change. It also did not persist bounded packet-mode diagnostics into the token lifecycle, so the bridge collapsed the failure into `MISSING_POST_MODE_FULL_PAYLOAD` without explaining whether the observed packet was quote, full, pre-mode, or unclassified.

## Fix

The runtime now classifies observation payloads by instrument class:

- `INDEX`: full requires `mode == "full"` or, if parser mode is absent, non-null `exchange_timestamp`.
- `INDEX`: equity depth is not required.
- `NSE_EQUITY`: full requires `mode == "full"` or complete depth semantics.
- post-mode causality uses local callback receipt time against `mode_request_succeeded_epoch`.
- full payloads received before mode success do not satisfy the gate.
- first post-mode full receipt timestamp is preserved and not overwritten.

The subscription lifecycle now includes bounded `latest_observation_packet` details:

```text
instrument_class
instrument_token
parsed_mode
has_ohlc
has_change
has_exchange_timestamp
has_depth
tradable
callback_receipt_epoch
source_tick_epoch
mode_request_succeeded_epoch
feed_session_id
reconnect_generation
structured_reason
```

Bridge failure reasons are now more specific:

```text
INDEX_FULL_PACKET_NOT_OBSERVED
INDEX_PACKET_MODE_UNPROVEN
POST_MODE_CALLBACK_NOT_OBSERVED
EQUITY_FULL_DEPTH_NOT_OBSERVED
```

## Validation

Focused tests:

```text
pytest -q tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_market_event_graph_lifecycle.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_market_event_graph_constituent_source.py tests/test_unified_live_validation_pr748_756_v1.py
```

Result:

```text
48 passed
```
