# Feed health truth matrix

| Case | Expected/observed test verdict | Status |
|---|---|---|
| Explicit selected dependency is healthy while an unrelated monitored option is degraded | Selected consumer can remain healthy; unrelated degraded symbol is listed in `monitored_degraded_symbols` | Covered by focused feed tests |
| Required selected option missing/stale/blocked | Fail closed | Covered by focused feed/symbol-safety tests |
| Websocket disconnected or explicit `global_feed_blocked` | Global blocker remains | Covered by existing focused tests |
| Aggregate `feed_ok=false` with requested symbol set and unrelated stale symbols | Does not alone veto requested set | Covered |
| Consumer contract for explicit INDEX_SPOT/INDEX_FUTURES/INDEX_OPTIONS/STOCK_SPOT/STOCK_OPTIONS states | Consumer contract is implemented; runtime snapshots now emit INDEX_SPOT and index/stock option health from explicit token/symbol maps. INDEX_FUTURES and STOCK_SPOT remain UNKNOWN because no authoritative identity source exists. Missing/invalid evidence normalizes to UNKNOWN; declared required domains fail closed; transport and monitored degradation affect `overall_state` | Offline producer and contract tests pass; unsupported domains and live incident replay remain UNKNOWN / partial |
| Real reported TCS-to-NIFTY incident causality | No live event evidence replayed | UNKNOWN |

No freshness threshold was widened. Required unknown symbol evidence fails closed.
