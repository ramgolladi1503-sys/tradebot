# Phase 1: Current State Audit (MIP)

## Brutally Honest Audit

### 1. Which files are real implementation?
- `core/intelligence/robots_gate.py`: Real implementation. Uses standard library correctly to gate HTTP fetchers.
- `core/intelligence/context_adapter.py`: Real implementation. Properly checks payload states and injects safely into `candidate["advisory_context"]`.
- `core/intelligence/validators/schemas.py`: Real typing/schemas using dataclasses.
- `core/intelligence/calibration/factors.py`: Real, contains the critical `__post_init__` bypass block locking out uncalibrated influence.
- `core/intelligence/calibration/relevance_model.py`: Real constraints wrapper.

### 2. Which files are scaffolding?
- `core/intelligence/fetchers/base.py` & `http_fetcher.py`: Scaffolding. Missing retry, backoff, timeouts, circuit breakers.
- `core/intelligence/storage/store.py`: Scaffolding. Saves to local text/jsonl files arbitrarily without integration into TradeBot's persistence/SQLite.
- `core/intelligence/extractors/base.py`: Scaffolding placeholder. Does no actual string parsing or HTML normalization.
- `core/intelligence/replay/intelligence_replay.py`: Pure scaffolding. Pretends to output forward volatility but has no actual integration with `tick_store`.
- `core/intelligence/knowledge/graph.py`: Scaffolding. Static lists simulating a graph without real resolution bindings.

### 3. Which reports are claims without code proof?
- The dashboard/reporting integration (Agent 10) was 100% claims. There is no Streamlit or UI code implemented.
- Replay calibration wiring (Agent 8) claims it measures volatility, but the code merely returns hardcoded mock floats `1.2`.

### 4. Which tests are too shallow?
- `tests/intelligence/test_mip_safety.py` tests the basic logic of `__post_init__` and `ContextAdapter`, but completely ignores rate limit logic, HTML parsing edge cases, DB persistence, JSON parsing, timeout handling, and source URL validation.

### 5. Which integrations are missing?
- **Persistence**: Missing SQLite table mapping.
- **Telemetry**: Missing structured logs to TradeBot's real telemetry engines (e.g. `observability/`).
- **Runner**: Missing the CLI orchestrator to actually schedule and run the fetchers.
- **Replay**: Missing direct connection to `core.market_data` or `tick_store.py` for actual option spread/volatility calculations.

### 6. Where are hidden heuristics still present?
- In `config.py`, defaults are hardcoded without explicit typing/validation on load.
- In `IntelligenceReplayEngine`, the `1.2` volatility multiplier and `[1.1, 1.3]` confidence interval are fake heuristics meant as scaffolding placeholders.

### 7. Where can intelligence accidentally influence execution/ranking?
- While `Factor.__post_init__` catches `execution_influence_allowed=True` bypasses, Python's dynamic nature means if a developer overrides it without using `build_uncalibrated_factor`, or if they edit the `candidate` dict directly *after* `ContextAdapter`, the protections could be bypassed.

### 8. What is blocking production readiness?
- No real HTML extraction.
- No real fetch retry/backoff limits (critical for not getting IP banned).
- No actual DB persistence to survive a reboot.
- No real telemetry to monitor source health.
- Lack of offline replay data connection means it can never escape the "UNCALIBRATED" state.
