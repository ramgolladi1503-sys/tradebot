# Phase 2: TradeBot Integration Map

## Existing Repositories and Integration Points

### 1. Persistence (SQLite/DB Layer)
- **`core/tick_store.py` & `core/trade_store.py`**: The canonical patterns for structured SQLite storage. The MIP must replicate this standard, potentially adding its own database (e.g., `mip_store.sqlite`) or integrating into the main analytical store using similar connection pooling and PRAGMA configurations.
- **`core/analytics/store.py`**: Contains offline tracking schemas. MIP replay logic should wire closely here to query forward volatility.

### 2. Telemetry and Observability
- **`core/decision_telemetry.py` & `core/reject_telemetry.py`**: Handle real-time JSONL emissions and event tracing.
- **`core/observability/tracing.py`**: A structured tracing module that the new MIP telemetry should utilize to log `fetch_started`, `extraction_succeeded`, etc.

### 3. Orchestration & Scheduler
- **`core/orchestrator.py` & `run_live_loop.sh`**: TradeBot operates on a rigid orchestration loop. The MIP fetcher will NOT execute within the hot path of `run_live_loop.sh` to prevent stalling the execution engine. It will operate as a separate cron-driven sidecar (`scripts/run_intelligence_pipeline.py`).

### 4. Candidate Lifecycle & Ranking
- **`core/candidate_pool.py` & `core/candidate_state_contract.py`**: Where candidates are born and mutated.
- **`core/candidate_ranking.py`**: The scoring system. MIP is completely locked out of this file unless a formal replay correlation bridges it.
- **`core/advisory_schema.py`**: The safest integration point for MIP context.

### 5. Replay Engine
- **`core/replay_engine.py`**: The official engine for evaluating historical strategy metrics. MIP's calibration engine (`core/intelligence/replay/intelligence_replay.py`) will hook into the dataset contracts used here to pull `OHLC` or tick-level data for option spread widening and candidate rejection rates.
