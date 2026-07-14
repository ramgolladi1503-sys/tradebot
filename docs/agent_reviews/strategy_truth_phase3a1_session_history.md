# Strategy Truth Phase 3A1 Evidence Correction

## IMPLEMENTATION DIRECTION
RIGHT

## approved objective
Resolve the Phase 3A1 ancestry, timestamp-classification and partial-session evidence inconsistencies without changing completed-bar semantics or strategy behavior.

## what was actually implemented
- Verified that `44e00eba482ed233082a48dd858c20e12ab3fbd3` is the direct parent of `e1da0fba4d3c7b16d33085171e3a7498735fba9c`.
- Corrected the recursive replay-manifest helper so numeric epoch timestamps are classified deterministically as seconds, milliseconds, microseconds, or nanoseconds instead of being guessed by bare `pd.to_datetime(...)`.
- Corrected the evidence-layer session classifications:
  - `SUITABLE_PARTIAL_UNDERLYING_SESSION` now means a genuine non-empty captured partial session with `1 <= legal_completed_bar_count < 375`.
  - `NO_LEGAL_COMPLETED_BARS` now covers files with valid OHLC schema but zero regular-session completed bars.
  - `UNSUPPORTED_SESSION_WINDOW` now covers files with timestamps outside the accepted regular-session window.
- Regenerated:
  - `docs/agent_reviews/strategy_truth_phase3a1_corpus_manifest.json`
  - `docs/agent_reviews/strategy_truth_phase3a1_checkpoints.json`
- Replaced the selected partial replay file with the lexicographically first valid non-empty captured partial session.

## architecture assessment
NECESSARY_MINIMAL. `core/session_bar_history.py` remains a narrowly scoped production module introduced by Phase 3A1. This corrective patch did not add new production architecture; it corrected evidence and classification around the existing module.

## commits
- Phase 2C semantic base: `44e00eba482ed233082a48dd858c20e12ab3fbd3`
- Phase 3A1 original commit: `e1da0fba4d3c7b16d33085171e3a7498735fba9c`
- Actual Phase 3A1 starting commit: `44e00eba482ed233082a48dd858c20e12ab3fbd3`

## ancestry result
- `git show -s --format='commit=%H%nparents=%P%nsubject=%s' e1da0fba4d3c7b16d33085171e3a7498735fba9c`
  - commit: `e1da0fba4d3c7b16d33085171e3a7498735fba9c`
  - parent: `44e00eba482ed233082a48dd858c20e12ab3fbd3`
  - subject: `strategy: add causal session bar history`
- `git merge-base --is-ancestor 44e00eba482ed233082a48dd858c20e12ab3fbd3 e1da0fba4d3c7b16d33085171e3a7498735fba9c`
  - exit status: `0`
- `git rev-list --ancestry-path 44e00eba482ed233082a48dd858c20e12ab3fbd3..e1da0fba4d3c7b16d33085171e3a7498735fba9c --oneline`
  - `e1da0fba strategy: add causal session bar history`

## files changed
- `tests/test_captured_market_session_replay.py`
- `docs/agent_reviews/strategy_truth_phase3a1_corpus_manifest.json`
- `docs/agent_reviews/strategy_truth_phase3a1_checkpoints.json`
- `docs/agent_reviews/strategy_truth_phase3a1_session_history.md`

## 1970 timestamp source
The old manifest contained `129` rows with parsed timestamps in `1970-01-01`. Every one of those rows came from tick-or-quote parquet files under `20260709/underlying/` with numeric `ts` values such as:

- raw value: `1783569405.740924`
- raw type: `float64`
- timestamp column: `ts`
- old parser path: bare `pd.to_datetime(series, errors="coerce")`
- old assumed unit: effectively nanoseconds by pandas inference
- old parsed timestamp: `1970-01-01T00:00:01.783569405+05:30`

Affected old classifications:
- `OPTION_QUOTE_OR_TICK_DATA`: `126`
- `UNDERLYING_TICK_DATA`: `3`

No `SUITABLE_FULL_UNDERLYING_SESSION` or `SUITABLE_PARTIAL_UNDERLYING_SESSION` row carried a 1970 timestamp.

## 1970 timestamp classification
Exact cause: `TICK_OR_QUOTE_TIMESTAMP_UNIT_MISMATCH`

After correction:
- parser used: `numeric_epoch_parse`
- assumed unit: `s`
- example corrected session date: `2026-07-09`
- the `1970` date no longer appears in suitable-candle summaries or tick/quote content dates

## date ranges
- Suitable underlying candle sessions:
  - earliest: `2024-05-30T09:15:00+05:30`
  - latest: `2026-07-10T15:29:00+05:30`
- Tick/quote market data:
  - earliest: `2026-07-09T09:26:45.740700006+05:30`
  - latest: `2026-07-09T15:39:01.652374029+05:30`
- Non-market artifacts:
  - earliest: `None`
  - latest: `None`
  - reason: no timestamp-bearing artifact files were present in the JSON artifact set
- All parsed timestamp-bearing files:
  - earliest: `2024-05-30T09:15:00+05:30`
  - latest: `2026-07-10T15:29:00+05:30`

The primary Phase 3A1 date range is the suitable-underlying-candle range above.

## zero-bar partial investigation
Investigated file:
- `20241101/underlying/BANKNIFTY_20241101.parquet`

Observed facts:
- row count: `60`
- raw first timestamp: `2024-11-01 18:00:00`
- raw last timestamp: `2024-11-01 18:59:00`
- raw timestamp type: `Timestamp`
- timezone: `Asia/Kolkata`
- path date: `2024-11-01`
- content date: `2024-11-01`
- expected regular session window: `2024-11-01T09:15:00+05:30` through `2024-11-01T15:29:00+05:30`
- timestamps inside accepted session window: `0`
- bars passing OHLC validation: `60`
- legal completed bars at final cutoff: `0`
- zero-bar reason: all rows are after-hours bars outside the accepted regular session window

Cause classification:
- `OUTSIDE_REGULAR_SESSION`

Final manifest classification:
- `NO_LEGAL_COMPLETED_BARS`
- rejection reason: `no_completed_bars_within_regular_session`

## non-empty partial session
Deterministic selected captured partial session:
- `20241212/underlying/BANKNIFTY_20241212.parquet`

Selection rule:
- `lexicographically_first_nonempty_partial` within the overall deterministic replay-corpus rule

Observed facts:
- single symbol: `BANKNIFTY`
- single session date: `2024-12-12`
- row count: `374`
- timeframe: `1m`
- duplicate timestamps: `0`
- invalid OHLC rows: `0`
- timestamps inside accepted session window: `374`
- legal completed bars at final cutoff: `374`
- final state: `partial_session=True`

## non-empty partial causal proof
For `20241212/underlying/BANKNIFTY_20241212.parquet`:
- `after_first_completed_bar` -> `open_price` is available
- `after_second_completed_bar` -> `previous_completed_close` is available
- `final_completed_bar` -> `completed_bar_count=374`
- `day_high` and `day_low` progress causally across checkpoints
- incremental replay equals batch replay at each deterministic checkpoint
- future mutation does not alter earlier checkpoint hashes or session-state fields
- no full-session completeness claim is made

## classification counts before and after
Before correction:
- suitable full underlying sessions: `998`
- suitable partial underlying sessions: `23`
- tick/quote files: `129`
- invalid timestamp files: `0`
- invalid OHLC files: `0`
- ambiguous files: `0`

After correction:
- all discovered files: `1811`
- market-data files: `1150`
- non-market artifacts: `661`
- suitable full underlying sessions: `998`
- suitable non-empty partial underlying sessions: `10`
- zero-legal-bar files: `2`
- unsupported-session-window files: `11`
- option candle files: `0`
- tick/quote files: `129`
- invalid schema files: `0`
- invalid timestamp files: `0`
- invalid OHLC files: `0`
- ambiguous files: `0`

## classification reconciliation
`661 + 998 + 10 + 2 + 11 + 0 + 129 + 0 + 0 + 0 + 0 = 1811`

This exactly matches `all_discovered_files=1811`.

## known source hash result
Rechecked and confirmed:
- `NSE_INDEX|Nifty 50_20260709.parquet`
  - expected: `89a0d9cc98ba6c6decf1d6a1f62fa8b82f80820b51205ae32f222287b7aa550d`
  - actual: `89a0d9cc98ba6c6decf1d6a1f62fa8b82f80820b51205ae32f222287b7aa550d`
- `NSE_INDEX|Nifty Bank_20260709.parquet`
  - expected: `8dfdc7b8a2c06ce46379d8f7f1cb59d10cd075bd34ceff0643c2b053ccdeb718`
  - actual: `8dfdc7b8a2c06ce46379d8f7f1cb59d10cd075bd34ceff0643c2b053ccdeb718`

## manifest and checkpoint hashes
- Manifest hash before correction: `4ce551f1be6447b5062849e6d8de9fe33d9f4d1320fef295d251b521535b654c`
- Manifest hash after correction: `3aea80971eda706cd9a6fd0e02c85167bee789797459bcdf2de52fddebd863ea`
- Manifest artifact file hash before correction: `8038d7ce83932914daf5a3e485001362df431845e824648b2e85b857285ea408`
- Manifest artifact file hash after correction: `fab40da5af394fc10872057b40bae718b360f367404e19eacfbd445d584f191c`
- Checkpoint artifact file hash before correction: `6622f4ee8ce8fc1e827ad5a8f3e8264ed7b554f259516a96883592c5c8b2a526`
- Checkpoint artifact file hash after correction: `f86abd9dfb95e35f0d70f9ee9737155c9827063d28c72b6aca42206c74283081`

## completed-bar contract result
Preserved. No production session-history semantics were changed. The corrective patch only changed manifest classification and evidence selection.

## session-state result
Preserved. `open_price`, `day_high`, `day_low`, `previous_completed_close`, and completed-bar-history metadata still come from the same Phase 3A1 completed-bar path.

## causality regression result
None found.

## incremental-versus-batch result
Preserved across the corrected selected replay corpus, including the newly selected non-empty partial session.

## lint baseline comparison
- The corrective Python changes are limited to `tests/test_captured_market_session_replay.py`.
- `ruff check tests/test_captured_market_session_replay.py` passes.
- No new lint violation was introduced on corrective task-owned changed lines.
- Repository-wide legacy lint debt outside this file remains out of scope and unchanged.

## focused tests and results
- `python -m pytest -q tests/test_captured_market_session_replay.py`
  - `13 passed, 1 warning in 168.14s`
- Required focused command:
  - `python -m pytest -q tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py tests/test_strategy_context_truth.py tests/test_candidate_phase2_semantic_ownership.py tests/test_candidate_phase2_ownership.py tests/test_strategy_missing_evidence_observability.py tests/test_strategy_missing_evidence_policy.py tests/test_strategy_profile_fail_closed.py tests/test_candidate_pool.py tests/test_candidate_pool_orchestrator.py`
  - `107 passed, 1 warning in 186.59s (0:03:06)`

## full-suite result
`python -m pytest -q` -> `1 failed, 5745 passed, 1 deselected, 935 warnings in 534.83s (0:08:54)`

## first failure
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- `RuntimeError:[AUTH] missing_kite_access_token`

The rerun remained identical to the established pre-existing auth failure.

## explicit non-claims
- No ATR short/long contract was defined.
- No support/resistance contract was defined.
- No range-width contract was defined.
- No movement strategy was changed.
- No temporal strategy conformance was implemented.
- No profitability or predictive edge was claimed.
- No option replay, backtesting, or WFA was performed.
- No live-readiness claim was added.
