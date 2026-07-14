IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Freeze an explicit, evidence-backed canonical contract for atr_short and atr_long without implementing runtime ATR propagation or changing strategy formulas.

WHAT WAS INVESTIGATED:
- All repository readers and writers of `atr_short` and `atr_long`
- Compression Breakout and Event Volatility Expansion strategy semantics
- Movement regime ATR-ratio usage
- Existing generic runtime ATR implementation
- Offline/research short-long ATR proxy implementations
- Existing tests and prior Phase 2A / Phase 3A1 evidence

ARCHITECTURE ASSESSMENT:
- No new runtime architecture was introduced.
- No ATR runtime propagation was added.
- No strategy formulas, thresholds, profiles, or candidate behavior were changed.
- This phase remains a semantic audit plus blocker evidence package.

STARTING COMMIT:
- `c92ee3782f8848d387a8349ebef5c655541cf01b`

FILES CHANGED:
- `docs/agent_reviews/strategy_truth_phase3a2_atr_contract.md`
- `tests/test_atr_contract_decision.py`

## complete writer-reader matrix

| field | current writer | current reader | consumer strategy | formula using the field | required or optional | semantic expectation | current runtime source | offline/research source | timeframe | lookback | smoothing | gap handling | session behavior | warm-up behavior | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `atr_short` | `core/movement_contract.py` declaration only; `core/runtime_snapshot_producer.py` pass-through only; no canonical runtime producer | `strategies/movement/compression_breakout.py`, `strategies/movement/event_volatility_expansion.py`, `core/movement_regime.py`, `core/orchestrator.py` missing-source marker | `compression_breakout_v1`, `event_volatility_expansion_v1`, regime classifier | `atr_short / atr_long` | required by the two strategies when used; optional in regime scoring | recent realized volatility leg for a short horizon | none; Phase 2A and 3A1 keep it missing | `core/orb_ohlcv_validation.py`, `scripts/backtest_all_strategies_available_data.py` compute `true_range.rolling(5, ...)` | runtime undefined; proxy uses completed 1m candles | runtime undefined; proxy uses 5 | runtime undefined; proxy uses simple rolling mean | runtime undefined; proxy silently zero-fills after rolling mean | runtime undefined; proxy resets per session | runtime undefined; proxy allows partial windows and zero fill | `UNDEFINED` |
| `atr_long` | `core/movement_contract.py` declaration only; `core/runtime_snapshot_producer.py` pass-through only; no canonical runtime producer | `strategies/movement/compression_breakout.py`, `strategies/movement/event_volatility_expansion.py`, `core/movement_regime.py`, `core/orchestrator.py` missing-source marker | `compression_breakout_v1`, `event_volatility_expansion_v1`, regime classifier | `atr_short / atr_long` | required by the two strategies when used; optional in regime scoring | slower realized-volatility baseline for comparison with `atr_short` | none; Phase 2A and 3A1 keep it missing | `core/orb_ohlcv_validation.py`, `scripts/backtest_all_strategies_available_data.py` compute `true_range.rolling(30, ...)` | runtime undefined; proxy uses completed 1m candles | runtime undefined; proxy uses 30 | runtime undefined; proxy uses simple rolling mean | runtime undefined; proxy silently zero-fills after rolling mean | runtime undefined; proxy resets per session | runtime undefined; proxy allows partial windows and zero fill | `UNDEFINED` |
| generic `atr` reference baseline | `core/indicators_live.py` via `compute_indicators(... atr_period=ATR_PERIOD ...)`; consumed into `core/market_data.py` and then `StrategyContext.atr` | not a direct `atr_short/atr_long` consumer, but the only canonical ATR family currently running in production | regime, trade builder, other non-Phase-3A2 consumers | simple 14-period ATR, not short/long pair | optional for these consumers | single-horizon live ATR | canonical runtime indicator output | none relevant to short/long | runtime indicator cadence from OHLC buffer; intended live intraday bar stream | `ATR_PERIOD`, default 14 | simple rolling mean over trailing true ranges | startup seed + warmup fallback logic for generic ATR only | tied to current runtime session buffer | requires enough bars for `compute_indicators` | `AUTHORITATIVE_RUNTIME_CONTRACT` for `atr` only, not for `atr_short` / `atr_long` |

## compression-breakout semantic audit

Source:
- `strategies/movement/compression_breakout.py:41-211`

Observed meaning:
- The setup requires `range_width_pct`, `atr_short`, and `atr_long` as required thesis evidence.
- It computes only a single-snapshot ratio: `atr_short / atr_long`.
- Compression evidence increases when `atr_short / atr_long < MAX_ATR_RATIO`.
- The current threshold is `MAX_ATR_RATIO = 0.75`.

Interpretation:
- The strategy is trying to measure short-horizon realized range contraction relative to a slower baseline.
- It does not currently encode a prior compressed state followed by later release.
- The current implementation is snapshot-only, not temporal-stateful.

Conclusion:
- Compression Breakout needs two causally completed ATR horizons with the same units and timeframe so that a truthful ratio can represent "recent compression vs slower baseline."

## event-volatility-expansion semantic audit

Source:
- `strategies/movement/event_volatility_expansion.py:38-211`

Observed meaning:
- The setup requires `atr_short`, `atr_long`, and `volume_z` as required thesis evidence.
- It computes only a single-snapshot ratio: `atr_short / atr_long`.
- Expansion evidence increases when `atr_short / atr_long > MIN_ATR_EXPANSION_RATIO`.
- The current threshold is `MIN_ATR_EXPANSION_RATIO = 1.15`.

Interpretation:
- The strategy is trying to measure recent realized volatility expansion relative to a slower baseline.
- It also uses a snapshot-only ratio today.
- It does not encode a distinct temporal "previously normal then expanding" state in the current generator.

Conclusion:
- Event Volatility Expansion needs the same kind of two-horizon realized-range measure as Compression Breakout, but applied on the opposite side of the ratio threshold.

## existing generic atr audit

Source:
- `core/market_data.py:1729-1736`
- `core/market_data.py:2798-2809`
- `core/indicators_live.py:9-56`

Findings:
- Production runtime computes only one ATR field: `atr`.
- `compute_indicators()` accepts one `atr_period` and returns one `out["atr"]`.
- The implementation is a simple trailing mean of true ranges over the last `atr_period` bars.
- No runtime code defines separate short and long ATR lookbacks.
- No runtime code names a short/long smoothing policy, session reset policy, or warm-up policy for `atr_short` / `atr_long`.

Result:
- Existing runtime ATR is authoritative only for the generic `atr` field.
- It does not establish the short/long contract.

## offline proxy audit

Sources:
- `core/orb_ohlcv_validation.py:133-145`
- `scripts/backtest_all_strategies_available_data.py:206-217`
- `tests/test_orb_ohlcv_validation.py:110-123`

Findings:
- Both proxy writers compute true range as `max(high-low, abs(high-prev_close), abs(low-prev_close))`.
- Both assign:
  - `atr_short = true_range.rolling(5, min_periods=3).mean().fillna(0.0)`
  - `atr_long = true_range.rolling(30, min_periods=5).mean().fillna(0.0)`
- These paths are explicitly offline validation or backtest utilities, not canonical runtime StrategyContext propagation.
- At least one test calls the Layer A output an `atr` proxy.

Result:
- 5/30 simple rolling ATR exists as proxy evidence only.
- Its partial-window and zero-fill behavior conflicts with the truthful missingness boundary accepted in Phase 2A and Phase 3A1.

## evidence hierarchy result

Applied priority:
1. Existing production contract used consistently by runtime consumers
2. Explicit versioned strategy specification or decision record
3. Existing strategy profile and tests
4. Existing strategy implementation semantics
5. Research implementation explicitly identified as canonical
6. Research proxy or example
7. Generic trading convention

Outcome:
- Level 1 exists only for generic `atr`, not `atr_short` / `atr_long`.
- No explicit versioned short/long decision record exists.
- Strategy profiles contain only thresholds (`0.75`, `1.15`), not indicator semantics.
- Strategy implementations prove only that both consumers expect a same-unit short/long ratio.
- The only concrete numerical short/long implementation is proxy-level evidence.

Therefore:
- Repository evidence is insufficient to freeze one authoritative short/long contract without an explicit decision.

## candidate contract comparison

### Candidate A
- Timeframe: 1-minute completed underlying session bars
- Short lookback: 5 bars
- Long lookback: 30 bars
- Smoothing: simple rolling mean of true range
- First session bar: `SESSION_LOCAL`
- Session behavior: `RESET_EACH_SESSION`
- Warm-up: strict full-window warm-up
- Advantages: exactly matches both discovered proxy writers
- Risks: only proxy evidence exists; current proxy behavior uses partial windows and zero fill that should not become runtime truth by accident
- Repository evidence: `core/orb_ohlcv_validation.py`, `scripts/backtest_all_strategies_available_data.py`
- Fits consumers: Compression Breakout, Event Volatility Expansion, Movement Regime

### Candidate B
- Timeframe: 1-minute completed underlying session bars
- Short lookback: 5 bars
- Long lookback: 30 bars
- Smoothing: Wilder recursive moving average
- First session bar: `SESSION_LOCAL`
- Session behavior: `RESET_EACH_SESSION`
- Warm-up: strict full-window warm-up
- Advantages: aligns with the repository's broader use of Wilder-style smoothing in ADX/RSI families
- Risks: no current short/long ATR implementation or test uses Wilder for these fields
- Repository evidence: `core/vectorized_signals.py`, `core/indicators_live.py`
- Fits consumers: Compression Breakout, Event Volatility Expansion, Movement Regime

### Candidate C
- Timeframe: runtime OHLC buffer bars at the existing indicator cadence
- Short lookback: 14 bars
- Long lookback: 30 bars
- Smoothing: simple rolling mean of true range
- First session bar: `SESSION_LOCAL`
- Session behavior: `RESET_EACH_SESSION`
- Warm-up: strict full-window warm-up
- Advantages: reuses the existing runtime `atr` family for the short leg
- Risks: the repository never defines `14/30` as the short/long pair; long lookback remains proxy-derived
- Repository evidence: `core/indicators_live.py`, `core/market_data.py`
- Fits consumers: Compression Breakout, Event Volatility Expansion, Movement Regime

## timeframe decision
- Not frozen.
- All defensible alternatives use completed underlying intraday bars.
- Repository evidence is not sufficient to prove whether the canonical timeframe must be explicitly 1-minute everywhere or the generic runtime indicator cadence.

## true-range decision
- Partially supported but not frozen as canonical for short/long.
- Both proxy writers use:
  - `max(high - low, abs(high - previous_close), abs(low - previous_close))`
- Generic runtime `atr` uses the same formula.
- `previous_close` is the previous completed bar close inside the same causal sequence.

## first-bar decision
- Not frozen.
- Proxy implementations effectively degrade the first row through shift-induced NaN and later zero fill.
- That is not acceptable as an implicit runtime contract.
- Cross-session previous close is not currently available under a dedicated Phase 3A2 contract name.

## short-lookback decision
- Not frozen.
- `5` appears only in proxy writers.
- No authoritative runtime or decision-record source promotes `5` from proxy to canonical contract.

## long-lookback decision
- Not frozen.
- `30` appears only in proxy writers.
- No authoritative runtime or decision-record source promotes `30` from proxy to canonical contract.

## smoothing decision
- Not frozen.
- Proxy evidence supports simple rolling mean.
- Broader indicator conventions elsewhere support Wilder-style smoothing for other indicators.
- No repository source resolves that conflict for `atr_short` / `atr_long`.

## warm-up decision
- Not frozen.
- Truth-preserving behavior argues for strict full-window warm-up with unavailable values before readiness.
- Existing proxies instead use partial warm-up and zero fill.
- No authoritative repository decision chooses one policy for runtime short/long ATR.

## session behavior decision
- Not frozen.
- Phase 3A1 provides session-bounded completed-bar history.
- No repository decision proves whether short/long ATR should reset per session or continue across sessions.
- Cross-session behavior would require a separately defined prior-session close contract that does not yet exist for this field pair.

## missing-bar policy
- Not frozen.
- The truthful boundary established in Phases 2A and 3A1 favors unavailable values over interpolation.
- No current short/long ATR contract defines behavior for missing bars, duplicate bars, non-finite OHLC, or partial sessions.

## output unit
- If frozen later, the only defensible unit is underlying price points.
- No repository evidence supports percent volatility under the names `atr_short` or `atr_long`.

## precision and determinism
- If frozen later, calculation should avoid rounding during computation and serialize deterministically only at evidence boundaries.
- No current short/long ATR contract states a rounding or hash policy.

## shared-contract compatibility result
- The two strategy consumers are semantically compatible with one shared family of fields.
- Both require a same-unit short-horizon versus long-horizon realized-range comparison over causal completed bars.
- This phase is not blocked by a consumer semantic collision.
- This phase is blocked because the repository does not yet provide enough authoritative evidence to choose one numerical contract.

## final contract or blocker

`PHASE3A2_BLOCKED_CONTRACT_DECISION_REQUIRED`

Reason:
- There is no authoritative repository source that resolves:
  - timeframe
  - short lookback
  - long lookback
  - smoothing
  - first-session-bar policy
  - warm-up policy
  - session-reset policy

The only explicit short/long implementation is proxy code. Promoting it directly would guess semantics from Level-6 evidence.

## runtime behavior preservation proof
- `tests/test_captured_market_session_replay.py:930-957` already proves truthful runtime context still exposes `atr_short is None` and `atr_long is None`.
- `tests/test_strategy_context_truth.py:257-276` proves runtime `atr` does not get copied into `atr_short` or `atr_long`.
- No production file was modified, so no runtime propagation path changed in this phase.

## focused test result
- `python -m pytest -q tests/test_atr_contract_decision.py tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py tests/test_strategy_context_truth.py tests/test_strategy_missing_evidence_policy.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
- Result: `72 passed in 341.86s (0:05:41)`

## additional discovered test result
- Discovered by searching for `atr_short`, `atr_long`, `atr_ratio`, `compression_breakout`, `event_volatility_expansion`, `true range`, and `Wilder` under `tests/`
- Additional command:
  - `python -m pytest -q tests/test_movement_contract.py tests/test_movement_regime.py tests/test_strategy_module_taxonomy_sync.py tests/test_strategy_spec_remaining_families.py`
- Result: `26 passed in 2.25s`

## static check result
- `python -m py_compile tests/test_atr_contract_decision.py` passed
- `ruff check tests/test_atr_contract_decision.py` passed
- `git diff --check` passed

## full-suite result
- `python -m pytest -q`
- Result: `1 failed, 5751 passed, 1 deselected, 934 warnings in 573.53s (0:09:33)`

## first failure
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- Failure text:
  - expected `"forced_cycle_error"` in `engine_cycle_status["last_error"]`
  - actual error remained `RuntimeError:[AUTH] missing_kite_access_token ... .runtime/kite_access_token`
- Classification: pre-existing auth-token failure pattern, consistent with the established Strategy Truth baseline

## risks
- The repository still lacks an explicit approved short/long ATR semantic contract.
- Runtime Phase 3A3 cannot proceed truthfully until one bounded alternative is explicitly approved.
- Proxy code still exists and could be mistaken for canonical truth without this blocker record.

## rollback
- Revert the Phase 3A2 evidence-only commit if this audit package itself is not wanted.
- No runtime rollback is necessary because no runtime behavior changes are introduced here.

## explicit non-claims
- No canonical short/long ATR contract was frozen.
- No runtime ATR propagation was implemented.
- No strategy score, threshold, candidate count, or candidate score was changed.
- No completed-bar history semantics were changed.
- No support/resistance or range-width contract was defined.
- No profitability, backtest, WFA, or candidate-production evidence was used to choose an ATR definition.
