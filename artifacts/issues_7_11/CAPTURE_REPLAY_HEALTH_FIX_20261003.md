# Captured replay health authority repair — 2026-10-03

**source_agent:** gsd
**action:** UPDATE_DOCS
**scope:** verification of the offline replay-source contract only
**repository base SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**PR #936:** excluded

## Defect and repair

`artifacts/issues_7_11/CAPTURE_REPLAY_20261001.md` records the direct attack: the Oct. 1 parquet does not contain receive-time or transport-health fields, but the historical replay source emitted `feed_ok=true`, `websocket_ok=true`, and `session_health=NORMAL`. The OHLCV bar replay also emitted a fixed `option_last_tick_age_sec=0.05`.

The authorized source change in `core/replay/governed_market_replay.py` makes parquet-backed replay feed/websocket state unknown, sets session health to `UNKNOWN`, marks feed/session health authority unavailable, and removes fabricated option age from bars. Recorded receipt timestamps still control event availability and observed latency. Hand-constructed `ReplayEvent` defaults remain unchanged.

## Attack and verification results

- Before patch, three targeted assertions failed: absent-receipt tick source claimed healthy feed/websocket; valid receipt still implied healthy feed/websocket; bar source supplied 50 ms option age.
- After patch, `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/replay` → **14 passed, 1 skipped, 1 warning in 3.65s**.
- Negative cases cover absent receive time, explicit receive time without transport health, malformed receive timestamp, and OHLCV bar inputs.
- Real-data replay source: `/Volumes/TradeBotData/live market capture/2026-10-01/upstox_full_ticks_20261001_stitched.parquet`, SHA-256 `c09998bf1807d4d8bc28bd3de5d4d56748269b30eabc5653ad4e8b2b8c4c5d1c`.
- Replayed 100 events for `NIFTY 22850 PE 06 OCT 26`: `feed_ok=None`, `websocket_ok=None`, `session_health=UNKNOWN`, receipt authority `UNAVAILABLE`, option age `None`.
- The governed engine processed 100 events/pulses with zero causality violations and zero observations when T-1 close/SMA were absent. It logged fail-closed T-1 prerequisite reasons. Temporary engine evidence was deleted after the run.
- Engine authority: read-only true; broker-write false; order false; orders placed zero; option execution replay unavailable.

## Scope and residuals

Only offline replay-source metadata and replay fidelity tests changed. No live feed producer, candidate/execution gate, strategy, risk, token configuration, broker/order path, credentials, or runtime wiring changed.

This closes the specific replay false-health assertion. It does not establish historical feed/websocket health, Issue 11 candidate isolation or global-latch cause, Issue 7 T-1 authority, Issue 8 CAS source-event authority, or live behavior. The observed token count does not certify or redefine the configured universe.
