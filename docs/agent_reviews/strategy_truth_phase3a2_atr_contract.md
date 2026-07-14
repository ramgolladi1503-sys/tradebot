IMPLEMENTATION DIRECTION:
RIGHT

APPROVED OBJECTIVE:
Freeze the explicitly approved atr_short_long_v1 contract without implementing runtime ATR calculation or changing strategy behaviour.

WHAT WAS ACTUALLY IMPLEMENTED:
- Added immutable contract module [core/atr_contract.py](/Users/madhuram/tradebot-strategy-atr-contract/core/atr_contract.py)
- Replaced the prior blocked-audit-only test with approved-contract invariant coverage in [tests/test_atr_contract_decision.py](/Users/madhuram/tradebot-strategy-atr-contract/tests/test_atr_contract_decision.py)
- Updated this decision record from blocked audit state to approved/frozen contract state while preserving the prior evidence and proxy rejection rationale

ARCHITECTURE CHANGE:
NONE

STARTING COMMIT:
- `c92ee3782f8848d387a8349ebef5c655541cf01b`

PHASE 3A2 AUDIT COMMIT:
- `eff89d5c11d7c0f7164b1727bcc52afd5e60343e`

FILES CHANGED:
- `core/atr_contract.py`
- `tests/test_atr_contract_decision.py`
- `docs/agent_reviews/strategy_truth_phase3a2_atr_contract.md`

## approval source
- Human-approved continuation instructions in the clean ATR-contract worktree explicitly selected Candidate A and specified the exact normative `atr_short_long_v1` contract.

## approved normative contract

ATR CONTRACT VERSION:
- `atr_short_long_v1`

SOURCE:
- Phase 3A1 completed underlying-index session bars

TIMEFRAME:
- `1m`

TRUE RANGE:
- First completed bar of session: `high - low`
- Later completed bars:
  - `max(high - low, abs(high - previous completed bar close), abs(low - previous completed bar close))`

FIRST SESSION BAR:
- `session_local_high_low`

SHORT LOOKBACK:
- `5` completed true-range observations

LONG LOOKBACK:
- `30` completed true-range observations

SMOOTHING:
- `simple_rolling_mean`

SHORT WARM-UP:
- `atr_short=None` until exactly five valid consecutive completed true-range observations exist

LONG WARM-UP:
- `atr_long=None` until exactly thirty valid consecutive completed true-range observations exist

PARTIAL-WINDOW POLICY:
- forbidden

ZERO-FILL POLICY:
- forbidden

SESSION POLICY:
- `RESET_EACH_SESSION`

MISSING-BAR POLICY:
- missing expected minute breaks continuity
- no interpolation
- no synthetic bar
- `atr_short` remains unavailable until five new consecutive valid completed bars exist after the gap
- `atr_long` remains unavailable until thirty new consecutive valid completed bars exist after the gap

INVALID-BAR POLICY:
- duplicate bar: fail closed
- out-of-order bar: fail closed
- invalid or non-finite OHLC: fail closed

PARTIAL-SESSION POLICY:
- permitted, but ATR remains unavailable until its strict contiguous warm-up is satisfied

OUTPUT UNIT:
- underlying index price points

PRECISION POLICY:
- no calculation rounding

SERIALIZATION:
- stable canonical serialization at evidence boundaries only

VERSIONING POLICY:
- future semantic change requires a new contract version
- `atr_short_long_v1` must not silently drift

## complete writer-reader matrix

| field | current writer | current reader | consumer strategy | formula using the field | required or optional | semantic expectation | current runtime source | offline/research source | timeframe | lookback | smoothing | gap handling | session behavior | warm-up behavior | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `atr_short` | declaration in `core/movement_contract.py`; runtime adapter pass-through in `core/runtime_snapshot_producer.py`; no canonical runtime writer | `strategies/movement/compression_breakout.py`, `strategies/movement/event_volatility_expansion.py`, `core/movement_regime.py`, `core/orchestrator.py` missing-source marker | `compression_breakout_v1`, `event_volatility_expansion_v1`, regime classifier | `atr_short / atr_long` | required in the two strategy consumers; optional in regime scoring | recent realized volatility leg over a short horizon | none; runtime remains missing | `core/orb_ohlcv_validation.py`, `scripts/backtest_all_strategies_available_data.py` proxy writers | approved as `1m` | approved as `5` | approved as simple rolling arithmetic mean | approved fail-closed continuity break on gaps | approved session reset | approved strict full-window warm-up | `AUTHORITATIVE_RUNTIME_CONTRACT` |
| `atr_long` | declaration in `core/movement_contract.py`; runtime adapter pass-through in `core/runtime_snapshot_producer.py`; no canonical runtime writer | `strategies/movement/compression_breakout.py`, `strategies/movement/event_volatility_expansion.py`, `core/movement_regime.py`, `core/orchestrator.py` missing-source marker | `compression_breakout_v1`, `event_volatility_expansion_v1`, regime classifier | `atr_short / atr_long` | required in the two strategy consumers; optional in regime scoring | slower realized-volatility baseline for comparison with `atr_short` | none; runtime remains missing | `core/orb_ohlcv_validation.py`, `scripts/backtest_all_strategies_available_data.py` proxy writers | approved as `1m` | approved as `30` | approved as simple rolling arithmetic mean | approved fail-closed continuity break on gaps | approved session reset | approved strict full-window warm-up | `AUTHORITATIVE_RUNTIME_CONTRACT` |
| generic `atr` | `core/indicators_live.py` via `compute_indicators(... atr_period=ATR_PERIOD ...)`, consumed by `core/market_data.py` | non-Phase-3A2 generic ATR consumers only | not the short/long pair | single-horizon ATR only | optional | live generic ATR | existing runtime indicator path | n/a | runtime indicator cadence | `ATR_PERIOD` | simple rolling mean | existing generic runtime behavior | existing generic runtime behavior | existing generic runtime behavior | unchanged generic runtime contract |

## compression-breakout semantic requirement
- `compression_breakout_v1` requires short-versus-long realized range contraction.
- It uses a single-snapshot `atr_short / atr_long` ratio and activates compression when that ratio is below `MAX_ATR_RATIO = 0.75`.
- This confirms the need for same-unit short and long ATR values computed over the same completed-bar timeframe.

## expansion semantic requirement
- `event_volatility_expansion_v1` requires short-versus-long realized volatility expansion.
- It uses a single-snapshot `atr_short / atr_long` ratio and activates expansion when that ratio exceeds `MIN_ATR_EXPANSION_RATIO = 1.15`.
- This confirms the same shared short/long ATR family as Compression Breakout.

## evidence hierarchy
1. The two production consumers share a short-versus-long volatility-ratio meaning.
2. Phase 3A1 establishes causal, session-scoped, completed one-minute bars.
3. Generic runtime ATR uses a simple trailing mean of true range.
4. Both concrete short/long proxy implementations use 5 and 30 bars.
5. No repository evidence supports Wilder smoothing for these fields.
6. No repository evidence supports 14/30 as the short/long pair.
7. No prior-session-close contract exists.
8. Fail-closed strict warm-up is required by the Strategy Truth boundary.

Required explicit statement:
- The 5/30 choice is an approved version-1 governance decision based on the strongest available repository evidence. It is not a claim of optimality, profitability, or universal trading convention.

## candidate results

CANDIDATE A RESULT:
- selected
- matches both concrete proxy writers on timeframe family, lookbacks, and smoothing family
- tightened by approved fail-closed warm-up and no-zero-fill policies

CANDIDATE B RESULT:
- rejected
- no repository evidence supports Wilder smoothing for `atr_short` / `atr_long`

CANDIDATE C RESULT:
- rejected
- no repository evidence supports `14/30` as the short/long pair

## proxy differences
- proxy keeps `rolling(5, min_periods=3)`
- proxy keeps `rolling(30, min_periods=5)`
- proxy keeps `fillna(0.0)`
- approved contract rejects all three behaviors
- proxy reconciliation is deferred to Phase 3A3 and later harness cleanup

## strict warm-up decision
- `atr_short` is unavailable until exactly five completed true-range observations exist
- `atr_long` is unavailable until exactly thirty completed true-range observations exist
- partial windows are not truthful enough for Strategy Truth runtime semantics

## missing-gap continuity decision
- a missing expected one-minute bar breaks contiguity
- no interpolation or synthetic recovery is permitted
- warm-up must restart from the next consecutive valid run

## session-reset rationale
- Phase 3A1 history is session-scoped and causal
- no approved prior-session-close contract exists for cross-session carry
- resetting each session avoids silently overloading `previous_completed_close`

## first-bar rationale
- first session bar has no prior completed in-session close
- therefore the approved first true range is only `high - low`

## runtime non-implementation proof
- runtime adapter still leaves `atr_short=None` and `atr_long=None`
- no changes were made to `core/runtime_snapshot_producer.py`, `core/market_data.py`, `core/session_bar_history.py`, or movement strategy files
- `core/atr_contract.py` contains only immutable contract data and invariant validation

## candidate behaviour preservation proof
- candidate fingerprints remain unchanged because no strategy, threshold, or runtime ATR propagation path changed
- direct-context setup fingerprint remains:
  - `opening_range_retest_v1 | BUY_CALL | 0.328053`
  - `compression_breakout_v1 | BUY_CALL | 0.470676`
  - `trend_pullback_v1 | BUY_CALL | 0.648584`
- runtime truthful ATR fields remain missing, so this phase introduces no new candidate behavior

## prior blocker audit retained
- Before explicit approval, repository evidence alone was insufficient to freeze the short/long ATR contract.
- That audit remains historically true.
- This document now supersedes the blocked result because the contract was explicitly approved.

## verdict
- `PHASE3A2_CONTRACT_FROZEN_WITH_PREEXISTING_TEST_FAILURE`

## focused test result
- `python -m pytest -q tests/test_atr_contract_decision.py tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py tests/test_strategy_context_truth.py tests/test_strategy_missing_evidence_policy.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
- `103 passed, 1 warning in 428.31s (0:07:08)`

## additional discovered test result
- discovered by searching for `atr_short`, `atr_long`, `atr_ratio`, `compression_breakout`, `event_volatility_expansion`, `movement_regime`, `true range`, and `Wilder`
- `294 passed, 1 warning in 249.53s (0:04:09)`

## static check result
- `python -m py_compile core/atr_contract.py tests/test_atr_contract_decision.py`
- `ruff check core/atr_contract.py tests/test_atr_contract_decision.py`
- `git diff --check`
- all passed

## full-suite result
- `python -m pytest -q`
- `1 failed, 5782 passed, 1 deselected, 935 warnings in 340.68s (0:05:40)`

## first failure
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- identical pre-existing auth-token baseline:
  - `RuntimeError:[AUTH] missing_kite_access_token`
  - `Missing token at /Users/madhuram/tradebot-strategy-atr-contract/.runtime/kite_access_token`
  - `Run scripts/kite_autologin_localhost.py to refresh token.`

## rollback
- revert only the approval follow-up commit if the approved contract artifact is rejected
- no runtime rollback is needed because no runtime behavior changed here

## explicit non-claims
- no runtime ATR calculation was implemented
- no `StrategyContext` mutation behavior changed
- no strategy thresholds or formulas changed
- no candidate ownership or Phase 2 logic changed
- no claim of profitability or indicator optimality is made
