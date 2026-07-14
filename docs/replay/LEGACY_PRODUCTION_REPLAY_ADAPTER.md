# Legacy Production Replay Adapter

## Objective
To provide a verifiable input boundary for historical, offline JSON lines data into the active legacy production pipeline (`Orchestrator._legacy_live_monitoring()`).

## Components
1. **Time Seam (`core.time_utils`)**: Replay clock injection seam allowing deterministic evaluation of freshness and timeouts.
2. **Replay Provider (`core.replay.legacy_market_data_provider`)**: `ReplayMarketDataProvider` consumes events, advances the clock, and pushes states to the production data stores.
3. **Execution Boundary (`scripts/run_legacy_production_replay.py`)**: A wrapper around the orchestrator to enforce safety conditions, mock out the broker adapter, and pipe data into the live monitoring cycle safely.

## Results
- Live state owners reused: `tick_store`, `ohlc_buffer`, `depth_store`.
- Exact runtime call chain reached: Yes, the legacy monitoring cycle runs deterministically.
- TradeBuilder result: Dependent on the specific replay event; TradeBuilder evaluated correctly on available features.
- Fallback Audit: Fallbacks are actively disabled to force raw signal evaluation.
- Verdict: `ACTIVE_LEGACY_PATH_PROVEN` using deterministic schema-only `FIXTURE_ONLY` datasets.
