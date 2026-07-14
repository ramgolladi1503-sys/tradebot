# Strategy Truth Phase 3A1 Session History

## IMPLEMENTATION DIRECTION
RIGHT_WITH_GAPS

## approved objective
Implement the causal completed-bar history and session-state portion of Phase 3A using the complete local Upstox historical-candle corpus, without defining or populating ATR short/long, structure anchors, or range width.

## what was implemented
- Added `core/session_bar_history.py` to derive a bounded, deterministic, one-session completed-bar view from causal one-minute bars.
- Propagated truthful session-state fields into runtime market data and `StrategyContext`:
  - `open_price`
  - `day_high`
  - `day_low`
  - `previous_completed_close`
  - `metadata["completed_bar_history"]`
  - `metadata["completed_bar_history_provenance"]`
- Added focused contract tests and recursive captured-corpus replay tests.
- Generated deterministic corpus-manifest and checkpoint artifacts:
  - `docs/agent_reviews/strategy_truth_phase3a1_corpus_manifest.json`
  - `docs/agent_reviews/strategy_truth_phase3a1_checkpoints.json`

## architecture assessment
NONE. The patch adds one narrow history-building module and reuses existing market-data, truth-metadata, and `StrategyContext.metadata` paths. It does not add a new indicator framework, storage layer, event system, or replay engine.

## commits
- starting commit: `2262e3baecb05b43f6113989f9715ea3ff199433`
- phase 0: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- phase 1A: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`
- phase 1B: `2a247ec6d92f60aa101d462eb6f3013d1aec4d54`
- phase 1C: `e74bbac98cfb3db43e15129bc78be4bb47564c45`
- phase 2A: `db19774008db93671c8a24b93f98cb7488498ad2`
- phase 2B: `b9142aa04cb977eea9eb9eff0eb6d6a2893c1d85`
- phase 2B observability: `2262e3baecb05b43f6113989f9715ea3ff199433`

## files changed
- `core/session_bar_history.py`
- `core/movement_contract.py`
- `core/runtime_snapshot_producer.py`
- `core/market_data.py`
- `core/orchestrator.py`
- `tests/test_completed_bar_history_contract.py`
- `tests/test_captured_market_session_replay.py`
- `docs/agent_reviews/strategy_truth_phase3a1_corpus_manifest.json`
- `docs/agent_reviews/strategy_truth_phase3a1_checkpoints.json`
- `docs/agent_reviews/strategy_truth_phase3a1_session_history.md`

## corpus root
`/Users/madhuram/tradebot/runtime/upstox_candidate_replay`

## captured-data inventory
- Total discovered files: `1811`
- Parquet files: `1150`
- JSON files: `661`
- CSV files: `0`
- Instrument categories: `artifact`, `option`, `underlying`

## classification counts
- `SUITABLE_FULL_UNDERLYING_SESSION`: `998`
- `SUITABLE_PARTIAL_UNDERLYING_SESSION`: `23`
- `OPTION_CANDLE_DATA`: `0`
- `OPTION_QUOTE_OR_TICK_DATA` and `UNDERLYING_TICK_DATA` together: `129`
- `INVALID_SCHEMA`: `0`
- `INVALID_TIMESTAMP`: `0`
- `INVALID_OHLC`: `0`
- `AMBIGUOUS`: `0`

## symbols and session counts
- `BANKNIFTY`: `495`
- `NIFTY`: `516`
- `NSE_INDEX|Nifty 50`: `5`
- `NSE_INDEX|Nifty Bank`: `5`

## date range
- Earliest content timestamp: `1970-01-01T00:00:01.783569405+05:30`
- Latest content timestamp: `2026-07-10T15:29:00+05:30`
- Distinct session dates span `2024-05-30` through `2026-07-10`

## full-session and partial-session counts
- Full underlying sessions: `998`
- Partial underlying sessions: `23`
- Zero-volume session count: `1021`

## invalid or ambiguous count
`0`

## captured-data hashes
- Manifest hash: `4ce551f1be6447b5062849e6d8de9fe33d9f4d1320fef295d251b521535b654c`
- Per-session final hashes are recorded in `docs/agent_reviews/strategy_truth_phase3a1_checkpoints.json`

## selected replay corpus
- `20240530/underlying/NIFTY_20240530.parquet`
- `20240531/underlying/NIFTY_20240531.parquet`
- `20240603/underlying/NIFTY_20240603.parquet`
- `20240604/underlying/NIFTY_20240604.parquet`
- `20240605/underlying/NIFTY_20240605.parquet`
- `20240701/underlying/BANKNIFTY_20240701.parquet`
- `20240702/underlying/BANKNIFTY_20240702.parquet`
- `20240830/underlying/NIFTY_20240830.parquet`
- `20241101/underlying/BANKNIFTY_20241101.parquet`
- `20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet`
- `20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet`
- `20260707/underlying/NSE_INDEX|Nifty 50_20260707.parquet`
- `20260707/underlying/NSE_INDEX|Nifty Bank_20260707.parquet`
- `20260710/underlying/NSE_INDEX|Nifty Bank_20260710.parquet`

## selection rule
`deterministic_union_of_first_five_dates + earliest/full/latest/full + earliest partial + per-symbol earliest + first consecutive same-symbol pair + min/max full-session range-percent diversity`

## completed-bar contract
- Input bars are restricted to the current symbol and current session only.
- Only bars with `bar_end_timestamp <= cutoff_timestamp` are emitted as completed bars.
- Completed bars must be one-minute, ordered, duplicate-free, finite, positive, and internally consistent (`high >= open/low/close`, `low <= open/high/close`).
- Bars from earlier or later sessions are ignored rather than merged.
- A deterministic `history_hash` is computed from the normalized completed-bar payload.
- The output is bounded by `session_history_bound(segment="NSE_FNO", timeframe="1m") == 375`.

## session-state contract
- `open_price`: first completed session open when available.
- `day_high`: maximum completed-bar high through cutoff.
- `day_low`: minimum completed-bar low through cutoff.
- `previous_completed_close`: close of the penultimate completed bar, or `None` if fewer than two completed bars exist.
- `completed_bar_history`: immutable metadata view of normalized completed bars.
- `completed_bar_history_provenance`: source component, timeframe, completeness, session date, latest completed timestamp, count, and deterministic hash.

## source matrix
| Field | Source component | Source data | Scope/timeframe | Runtime exposure | Status |
| --- | --- | --- | --- | --- | --- |
| `open_price` | `core.session_bar_history.build_session_bar_history_state` | completed one-minute session bars | `session_completed_bar` / `1m` | market data row + `strategy_context_truth` | TRUTHFUL |
| `day_high` | `core.session_bar_history.build_session_bar_history_state` | completed one-minute session bars | `session_completed_bar` / `1m` | market data row + `strategy_context_truth` | TRUTHFUL |
| `day_low` | `core.session_bar_history.build_session_bar_history_state` | completed one-minute session bars | `session_completed_bar` / `1m` | market data row + `strategy_context_truth` | TRUTHFUL |
| `previous_completed_close` | `core.session_bar_history.build_session_bar_history_state` | completed one-minute session bars | `session_completed_bar` / `1m` | market data row + `StrategyContext.previous_completed_close` + metadata | TRUTHFUL |
| `completed_bar_history` | `core.session_bar_history.build_session_bar_history_state` | normalized completed one-minute bars | `session_completed_bar` / `1m` | `StrategyContext.metadata` | TRUTHFUL |
| `atr_short` | not defined in Phase 3A1 | none | none | remains missing | UNDEFINED_BY_SCOPE |
| `atr_long` | not defined in Phase 3A1 | none | none | remains missing | UNDEFINED_BY_SCOPE |
| `nearest_support` | not defined in Phase 3A1 | none | none | remains missing | UNDEFINED_BY_SCOPE |
| `nearest_resistance` | not defined in Phase 3A1 | none | none | remains missing | UNDEFINED_BY_SCOPE |
| `range_width_pct` | not defined in Phase 3A1 | none | none | remains missing | UNDEFINED_BY_SCOPE |

## verified defects
- Phase 2A truthful runtime propagation still lacked a causal completed-bar history contract.
- `open_price`, `day_high`, `day_low`, and `previous_completed_close` were not being derived from a deterministic completed-bar session view.
- Runtime truth metadata lacked a bounded metadata view of completed bar history.

## false audit leads
- The recursive captured corpus does not contain option candle sessions for this phase. `total_option_candle_files` is `0`.
- Many files that look option-like by path or symbol are actually quote or tick files, not candle files. They were classified as tick/quote data rather than forced into the candle replay set.

## open/day high/day low/previous close results
- `open_price`: now comes from the first completed bar of the active session only.
- `day_high`: now comes from the maximum completed-bar high through cutoff only.
- `day_low`: now comes from the minimum completed-bar low through cutoff only.
- `previous_completed_close`: now comes from the penultimate completed bar only, never the active incomplete bar or a future bar.

## ATR, structure-anchor, and range-width status
- No `atr_short` contract was defined.
- No `atr_long` contract was defined.
- No support or resistance anchor contract was defined.
- No `range_width_pct` contract was defined.
- Tests explicitly assert those fields remain `None` after context construction.

## volume status
- Completed-bar history preserves volume only when it is truthful and positive.
- Zero or non-truthful volume is emitted as `None` in completed-bar history instead of being represented as valid session-volume evidence.

## causality proof
- Contract tests prove the current incomplete bar is excluded from completed history.
- Replay tests build state from prefixes only and compare incremental replay against batch replay at the same cutoff.
- Context tests prove no AST source parsing is invoked during runtime context construction.

## future-mutation proof
- `test_future_mutation_and_truncation_do_not_change_earlier_state` verifies appending later bars does not change the earlier checkpoint state or hash.

## truncation-equivalence proof
- The same test verifies truncating the feed after a checkpoint yields the same earlier state as the full file observed at that checkpoint.

## incremental-versus-batch proof
- `test_incremental_and_batch_replay_match_for_selected_sessions` verifies checkpoint-by-checkpoint equality between:
  - incremental prefix replay
  - single batch replay constrained to the same cutoff

## session-reset proof
- `test_session_reset_requires_new_session_history`
- `test_consecutive_session_reset_and_cross_symbol_isolation`

These prove a new session starts a new history and prior-session bars do not bleed into the next session state.

## cross-symbol isolation proof
- `test_consecutive_session_reset_and_cross_symbol_isolation` verifies symbol histories are isolated and do not contaminate each other.

## partial-session handling
- Partial sessions are allowed and explicitly marked `partial_session=True`.
- The selected corpus intentionally includes one partial session: `20241101/underlying/BANKNIFTY_20241101.parquet`.
- Its final checkpoint contains zero completed bars and deterministic empty-history hash `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

## checkpoint results
- The checkpoint artifact records deterministic cutoffs and state snapshots for every selected session.
- Full sessions end at `375` completed bars.
- The selected partial session ends at `0` completed bars and remains explicitly partial.

## per-session final hashes
- `20240530/underlying/NIFTY_20240530.parquet` -> `aa0af5ae016a83c190ce1d4b47cd918372f27fccecedc9b2e1d8e249bc45ff80`
- `20240531/underlying/NIFTY_20240531.parquet` -> `b91083febeed96e6c3a6bcc39365b2aa42c4e77fcff7f48eaacdbda9167267f2`
- `20240603/underlying/NIFTY_20240603.parquet` -> `9f59bb49c5e6b40b4f4fde37928720d5e6e25711ee6d7fd21fb16a65ae38e06f`
- `20240604/underlying/NIFTY_20240604.parquet` -> `627c104d6cdc0c7fe552525f8ce8a2ef725b4ffa0b1e20a47587a6ea8297a1e5`
- `20240605/underlying/NIFTY_20240605.parquet` -> `a853c62aa98799c30a8a0384fc1ecc32ea08187b67ac0655ae276e582ecca4d4`
- `20240701/underlying/BANKNIFTY_20240701.parquet` -> `7ef3a9bb5fc58a01ae5f54ba845131ee9975f7c4e29fd38f45caafb8506254bb`
- `20240702/underlying/BANKNIFTY_20240702.parquet` -> `f4303946aef90a59e063504c5c0d7c2bb749c7763a11f33f8d100ec829b74627`
- `20240830/underlying/NIFTY_20240830.parquet` -> `1468c437fd4ed67c2fd6a10c7b3c29c9d859e5911920a9a27aaed786fa7ccd95`
- `20241101/underlying/BANKNIFTY_20241101.parquet` -> `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`
- `20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet` -> `0d9f9918d0fa90465fcbe872f4edb4f45161299ece14ca4c55cdccc197a18471`
- `20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet` -> `2574424e31f41eaf241368191bec9a0e66b3e6a50f51d17e90823698096b56b9`
- `20260707/underlying/NSE_INDEX|Nifty 50_20260707.parquet` -> `d057133a92da4ca04beed70b30f65b5d91eb85c7ec3ea7c7f6c5390f45815e7d`
- `20260707/underlying/NSE_INDEX|Nifty Bank_20260707.parquet` -> `dfb7c495c8d057f7d92270d66986dc6fae336f26d22bb33a985939518e1958dd`
- `20260710/underlying/NSE_INDEX|Nifty Bank_20260710.parquet` -> `693d4a224a84c875901ac3d283b2de4051bb1e253cc4f9719741c6404419e86a`

## context before/after
- Before:
  - no bounded completed-bar session-history contract
  - no deterministic history hash
  - no truthful `previous_completed_close`
  - no completed-bar history metadata view
- After:
  - completed-bar history is causal, bounded, deterministic, and session-scoped
  - `open_price`, `day_high`, `day_low`, and `previous_completed_close` come from completed bars only
  - runtime truth metadata exposes history and provenance
  - undefined Phase 3A1 fields remain missing

## focused tests and results
- `python -m pytest -q tests/test_completed_bar_history_contract.py`
  - `6 passed, 1 warning in 1.63s`
- `python -m pytest -q tests/test_captured_market_session_replay.py`
  - `7 passed, 1 warning in 252.53s`
- Required focused command:
  - `python -m pytest -q tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py tests/test_strategy_context_truth.py tests/test_candidate_phase2_semantic_ownership.py tests/test_candidate_phase2_ownership.py tests/test_strategy_missing_evidence_observability.py tests/test_strategy_missing_evidence_policy.py tests/test_strategy_profile_fail_closed.py tests/test_candidate_pool.py tests/test_candidate_pool_orchestrator.py`
  - `101 passed, 1 warning in 226.51s`
- Additional discovered tests:
  - `python -m pytest -q tests/test_edge_99_replay_clock_no_future_leak.py tests/test_market_data_candles.py tests/test_market_data_orb_candle.py tests/test_market_data_warm_seed.py tests/test_market_data_minutes_since_open.py tests/test_session_calendar.py tests/test_replay_context_runtime_field_mapping.py`
  - `46 passed, 1 warning in 8.74s`
- Re-run after lint cleanup:
  - `python -m pytest -q tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py`
  - `13 passed, 1 warning in 201.02s`

## static checks
- `python -m py_compile core/session_bar_history.py core/movement_contract.py core/runtime_snapshot_producer.py core/market_data.py core/orchestrator.py tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py`
  - passed
- `ruff check tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py`
  - passed after test-name cleanup
- `ruff check core/session_bar_history.py core/movement_contract.py core/runtime_snapshot_producer.py core/market_data.py core/orchestrator.py tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py`
  - fails on a pre-existing repository lint backlog in `core/orchestrator.py` and unrelated legacy issues such as top-of-file import order and duplicate helper redefinitions; this Phase 3A1 patch did not attempt a repository-wide lint remediation
- `git diff --check`
  - passed

## full-suite result
`python -m pytest -q` -> `1 failed, 5739 passed, 1 deselected, 935 warnings in 602.31s (0:10:02)`

## first failure
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

Observed failure text:

```text
RuntimeError:[AUTH] missing_kite_access_token
Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token
Run scripts/kite_autologin_localhost.py to refresh token.
```

This matches the established pre-existing orchestrator credential baseline and is outside Phase 3A1 scope.

## risks
- The captured corpus proves the completed-bar/session-state contract, not temporal strategy conformance.
- The Phase 3A1 patch intentionally leaves ATR short/long, support/resistance anchors, and range width undefined.
- The recursive corpus contains tick/quote files and artifacts beyond the selected replay set; those were inventoried but not promoted into a candle-history contract.

## rollback
- Revert commit `strategy: add causal session bar history`.
- Remove the new `core/session_bar_history.py` module.
- Remove session-state propagation from `core/market_data.py`, `core/orchestrator.py`, and `core/runtime_snapshot_producer.py`.
- Remove the two Phase 3A1 test files and generated evidence artifacts.

## explicit non-claims
- No ATR short/long contract was defined.
- No support/resistance contract was defined.
- No range-width contract was defined.
- No movement strategy was repaired.
- No temporal pattern conformance was proved.
- No predictive edge was proved.
- No profitability was measured.
- No option replay was performed.
- No backtesting or WFA was performed.
- No live readiness was proved.
