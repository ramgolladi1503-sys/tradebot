# Issues 7–11 captured-data replay — 2026-10-01

**source_agent:** gsd
**action:** UPDATE_DOCS
**scope:** offline, read-only captured-data inspection and replay evidence
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**PR #936:** excluded

## Input identity

- Stitched ticks: `/Volumes/TradeBotData/live market capture/2026-10-01/upstox_full_ticks_20261001_stitched.parquet`
- SHA-256: `c09998bf1807d4d8bc28bd3de5d4d56748269b30eabc5653ad4e8b2b8c4c5d1c`
- Stitch summary: `/Volumes/TradeBotData/live market capture/2026-10-01/stitching_summary_20261001.json`
- Summary SHA-256: `982a2ae409347aa4a17f015d693abb5f848854469012294c66128d9507552044`
- Summary reports 389/389 valid chunks, 3,796,552 ticks, and 167 observed tokens.
- Parquet scan independently counted 3,796,552 rows, 167 token/symbol pairs, zero null timestamps, zero empty tokens, and zero empty symbols. No token mapped to multiple symbols and no symbol mapped to multiple tokens in this file.
- Schema: `ts`, `token`, `symbol`, `ltp`, `bid`, `ask`, `vol`, `oi`, `depth`. No receive timestamp, websocket state, subscription transition, or source-event ID/payload hash is present.
- Event timestamps span `2026-10-01 08:58:04 IST` through `15:41:01 IST`. The common initial option gap from about `08:59:52` to `09:11:01 IST` is present across many tokens; it coincides with the early capture window and is not sufficient evidence of a feed outage.

## Governed replay probe

The existing `UpstoxTickReplaySource` streamed 100 events for `NIFTY 22850 PE 06 OCT 26`; `GovernedMarketReplayEngine` ran in `EXACT_REPLAY` mode with no T-1 daily close or SMA supplied. Evidence output was confined to a temporary directory, removed when the probe ended.

- Events: 100; first `08:58:04.506916 IST`, last `09:16:00.415769 IST`.
- Source receipt authority: `UNAVAILABLE`; event-age value: `None`.
- Replay result: 100 processed, 100 pulses, zero observations, zero causality violations.
- Three T-1-dependent strategies logged fail-closed reasons: `MISSING_T_MINUS_1_FUTURES_PREREQUISITES` and `MISSING_T_MINUS_1_OVERNIGHT_PREREQUISITES`.
- Authority flags: `read_only=true`, `broker_write_authority=false`, `order_authority=false`, `orders_placed=0`, `option_execution_replay=UNAVAILABLE`.

## Interpretation and limits

The replay demonstrates that this capture can exercise a deterministic event path and that the replayed session remains fail-closed when T-1 values are absent. It does not prove that valid T-1 values were available or correctly staged on October 1.

The replay source currently emits `feed_ok=true`, `websocket_ok=true`, and `session_health=NORMAL` even when the parquet has no receive-time or transport-health evidence. These are replay defaults, not observations from the October 1 runtime. Therefore this replay itself cannot prove Issue 11 feed health, candidate-level fault isolation, websocket continuity, or the initiating cause of the captured `global_feed_blocked=true` latch. Run-matched saved feed/runtime artifacts separately identify terminal recovery/auth blocking states; see `CAPTURE_CORPUS_RECHECK_20261003.md`.

The capture also cannot establish Issue 8 CAS source-event identity or a verified prior-session interval. Its 167 observed tokens are not a comparison against the configured token universe and do not redefine token policy. No rows were written to the capture, no broker APIs or orders were used, and no live runtime was started.

## Reproduction and validation

Input hashes were computed with `shasum -a 256`. Parquet schema, row count, null identity/time counts, and token/symbol cardinalities were inspected with PyArrow `ParquetFile.iter_batches` over only `ts`, `token`, and `symbol`. The 100-event replay used `UpstoxTickReplaySource` and `GovernedMarketReplayEngine` from `core/replay/governed_market_replay.py`; the engine evidence root was a temporary directory.

This is an offline evidence note, not a new test, configuration change, live certification, or execution-readiness claim.
