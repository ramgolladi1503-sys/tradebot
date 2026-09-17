# Upstox Daily Live Market Tick Capture & Post-Market Stitching Pipeline

mode: SIM
candidate_id: 912-upstox-daily-live-capture-and-stitch
decision: add_upstox_daily_live_capture_and_stitch_pipeline
reason: Add automated crash-resilient Upstox WebSocket V3 tick capture, atomic Parquet chunk flush, full CAS capture through 15:40 IST, and automated master stitching at 15:41 IST.
timestamp: 2026-09-17T03:15:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/912-upstox-daily-live-capture-and-stitch.md

## Agent Work Contract

PR #912 only. Add `scripts/upstox_daily_live_capture_and_stitch.py`, `scripts/run_daily_upstox_pipeline.sh`, `scripts/stitch_today_market_data.py`, `tests/test_upstox_daily_live_capture.py`, `docs/data_capture/upstox_daily_live_capture_pipeline.md`, and this review evidence file.

## Scope Guard

In scope:
- `scripts/upstox_daily_live_capture_and_stitch.py`
- `scripts/run_daily_upstox_pipeline.sh`
- `scripts/stitch_today_market_data.py`
- `tests/test_upstox_daily_live_capture.py`
- `docs/data_capture/upstox_daily_live_capture_pipeline.md`
- `docs/agent_reviews/912-upstox-daily-live-capture-and-stitch.md`

Out of scope:
- Live broker order routing, account trading execution, strategy threshold modifications, risk gate weakening, production kill switches.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The pipeline provides purely read-only market tick capture and offline master file stitching.
- Zero broker trade authority: order placement, modification, and cancellation APIs are completely absent and forbidden.
- Secret safety: Tokens are read strictly via environment variables (`UPSTOX_ACCESS_TOKEN`) and never hardcoded or emitted.
- Concurrency control: OS-level single instance locking (`/tmp/upstox_daily_pipeline.lock`) blocks multiple streamer collisions.
- Full CAS discovery: Continuous WebSocket capture through 15:40:59 IST captures end-of-day price formation.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Atomic 60-second PyArrow Snappy Parquet chunk writing isolates crash risk from the master dataset.
- Clean deduplication on `[ts, token]` at post-market stitching guarantees 0 duplicate ticks.
- Dynamic ATM $\pm 10$ options contract resolution selects nearest active weekly/monthly expiry contracts without manual intervention.
- Automated retrieval of official 1-minute OHLCV index candles (`indices_1m_YYYYMMDD.parquet`) provides immediate cross-validation against tick aggregation.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- Runnable streaming pipeline, shell launcher wrapper, historical re-stitching CLI, and comprehensive test suite implemented and verified.
- Production storage configured to `/Volumes/TradeBotData/live market capture/` with graceful fallback to `.runtime/market_data/`.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- `pytest -v tests/test_upstox_daily_live_capture.py`: 5 passed.
- `python3 -m py_compile scripts/upstox_daily_live_capture_and_stitch.py scripts/stitch_today_market_data.py`: PASS.
- `is_order_action = false`, `broker_api_called = false`, `read_only = true`.
- Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_upstox_daily_live_capture.py
python3 -m py_compile scripts/upstox_daily_live_capture_and_stitch.py scripts/stitch_today_market_data.py
git diff --check
```

## Runtime Proof Required After Merge

The launcher script runs at 08:58 AM IST on market trading days to stream live ticks and stitch at 15:41 PM IST.

## What This PR Does Not Prove

This PR does not prove strategy profitability or alpha. It provides high-fidelity, crash-proof tick and order book capture.

## Human Approval

Approved by human operator for merge, data capture automation, and read-only market streaming.

## High-Risk Path Review

N/A - does not modify files under config/, core/execution/, core/risk/, core/broker/, or strategies/.

## Evidence Contract

- mode: SIM
- candidate_id: 912-upstox-daily-live-capture-and-stitch
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-09-17T03:15:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
