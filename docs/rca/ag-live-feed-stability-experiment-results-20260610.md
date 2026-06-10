# AG Live Feed Stability Experiment Results (2026-06-10)

## Objective
Run a safe live audit-only feed-stability experiment during market hours to address Kite WebSocket disconnect loops, Twisted `ReactorNotRestartable` errors, enforce strict tick/depth/option freshness checks, and resolve high CPU spin after feed failures.

## Verdict
**PASS**

The live experiment successfully connected to Kite, validated tick data flow, and kept candidate generation/evaluation in check without executing any order placements or exhibiting runaway CPU/Twisted reactor restart loops.

## Run Context
- **Branch**: `ag/live-feed-stability-experiment-20260610`
- **Run ID**: `ag_feed_stability_live_soak_20260610_152051`
- **Environment**: `LIVE_AUDIT_ONLY=1`, `ALLOW_LIVE_ORDERS=0`, `LIVE_TRADING_ENABLED=false`

## Key Metrics
The following metrics were compiled from the live run log (`runtime/live_observation/ag_feed_stability_live_soak_20260610_152051.log`):

| Metric | Count |
| --- | --- |
| **ReactorNotRestartable count** | 0 |
| **WS 1006 count** | 0 |
| **feed_ok true count** | 5 |
| **feed_ok false count** | 18 |
| **DEPTH_STALE count** | 18 |
| **LTP_STALE count** | 8 |
| **OPTION_TICKS_UNVERIFIED count** | 18 |
| **WARMUP_INCOMPLETE count** | 18 |
| **PHASE2 raw_count=0 count** | 26 |
| **PHASE2 raw_count>0 count** | 0 |
| **fallback_executable true count** | 0 |
| **real order placement count** | 0 |

## Observations
1. **Safety Enforced**: No real order placement was attempted or executed (order_risk.txt is empty, 0 bytes).
2. **Phase2 Cleanliness**: Phase2 raw_count remained strictly 0 when the feed state went invalid.
3. **No Reactor Storms**: Zero instances of `ReactorNotRestartable` or Twisted connection thread loops were observed.
4. **Feed Freshness Guard**: The feed evaluated as `feed_ok=True` only when all strict option and depth freshness requirements were successfully met.
