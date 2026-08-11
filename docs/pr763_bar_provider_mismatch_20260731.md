# PR #763 Bar Provider Mismatch Diagnostic - 2026-07-31

## Scope

Worktree: `/Users/madhuram/tradebot-unified-live-validation-pr748-756-v1`

Branch: `campaign/unified-live-validation-pr748-756-v1`

Previous bounded run ID: `unified-pr748-756-20260731-c70cc139b336-live-b47c598b`

Previous manifest SHA: `e60a75163ebdc8505b90c81d89ef8b5cdc820f1297ed912ede8ec501fb032050`

Previous repair head: `9f1e173035455e31b5cb3a1cb6769b46b175fd80`

## Proven Root Cause

The bounded run proved the live callback chain was working:

- observation generation: `0`
- feed generation: `0`
- generation match: `true`
- NIFTY accepted full callbacks: `10`
- constituent accepted full callbacks: `165`
- full-payload identities: `51`

The downstream bridge still rejected the completed bar as `BAR_PROVIDER_MISMATCH`.

That was a provenance-loss defect, not a wrong-broker-input defect.

## Incoming Live Tick Provenance

The live shadow tick path supplied:

- `provider = kite`
- `token_domain = kite_instrument_token`
- `universe_hash = authoritative contract hash`
- `symbol = <symbol>`
- `packet_kind = <packet kind>`

The write call in `core/market_event_graph_live_ohlc_buffer.py` passed these fields into `OhlcBuffer.update_tick(...)` through `provenance`.

## Pre-Fix Bar Provenance

Before the repair, `core/ohlc_buffer.py::_merge_live_bar_provenance()` persisted only:

- `source_type`
- `live_feed_session_id`
- `reconnect_generation`
- `instrument_token`
- `payload_mode`
- `first_live_tick_epoch`
- `last_live_tick_epoch`
- `historical_seed`
- `replay_fixture`
- `non_live_fallback`
- `recovered_synthetic`

It dropped:

- `provider`
- `token_domain`
- `universe_hash`
- `symbol`
- `packet_kind`

The bridge later expected those provenance fields when validating completed bars, so the bar was rejected as `BAR_PROVIDER_MISMATCH`.

## Files Changed

- `core/ohlc_buffer.py`
- `tests/test_market_event_graph_live_ohlc_buffer.py`
- `docs/pr763_bar_provider_mismatch_20260731.md`

## Regression Results

Focused direct buffer tests and bridge tests are added for:

- provenance field survival;
- same-minute updates preserving immutable identity;
- conflicting identity failing closed;
- provenance-free callers remaining compatible;
- historical seed behavior remaining unchanged;
- live-provenance bars staying valid for bridge checks.

The repaired path should preserve provider/token-domain/universe/symbol/packet-kind across live minute bars while refusing to silently merge conflicting immutable identity fields.
