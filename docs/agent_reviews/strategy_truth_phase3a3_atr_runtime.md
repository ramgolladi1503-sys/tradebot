IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Safely restore the committed Phase 3A2 evidence document when the only uncommitted change is the aborted Phase 3A3 handback, then implement atr_short_long_v1 over the Phase 1A completed-bar history.

RESTORATION RESULT:
The uncommitted aborted Phase 3A3 handback was discarded from the tracked Phase 3A2 evidence document. The committed Phase 3A2 evidence at HEAD was restored without changing commit history.

WHAT WAS ACTUALLY IMPLEMENTED:
- Added the narrow canonical ATR runtime calculator in [core/session_atr.py](/Users/madhuram/tradebot-strategy-atr-contract/core/session_atr.py).
- Wired `core.market_data.fetch_live_market_data` to populate `atr_short`, `atr_long`, and canonical provenance from Phase 3A1 completed-bar history.
- Wired `core.orchestrator._strategy_context_snapshot_metadata` to surface the same runtime ATR truth and provenance.
- Preserved the runtime context adapter and direct-context candidate fingerprint.
- Added focused runtime, replay, and proof tests plus the final evidence doc.
- Restored the committed Phase 3A2 evidence document before any Phase 3A3 work continued.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING COMMIT:
7d54de54347a152f003f05ce2b133efdbb58e68b

PHASE 3A3 COMMIT:
86651f08b8f880ee3d9c0c7ed131d4390f6e82c2

FILES CHANGED:
- `core/session_atr.py`
- `core/market_data.py`
- `core/orchestrator.py`
- `tests/test_atr_contract_decision.py`
- `tests/test_session_atr_runtime.py`
- `tests/test_captured_atr_replay.py`
- `tests/test_phase3a3_atr_proofs.py`
- `docs/agent_reviews/strategy_truth_phase3a3_atr_runtime.md`

PHASE 3A2 RESTORATION RESULT:
- The committed Phase 3A2 evidence document was restored to its HEAD content before the Phase 3A3 runtime work was finalized.
- The Phase 3A2 wording-correction claim was not committed; `docs/agent_reviews/strategy_truth_phase3a2_atr_contract.md` remains identical to the frozen contract commit `7d54de54347a152f003f05ce2b133efdbb58e68b`.
- The runtime evidence now lives only in this Phase 3A3 document.

CALCULATION OWNER:
`core.session_atr.calculate_session_atr_state`

RUNTIME WRITER:
`core.market_data.fetch_live_market_data`

RUNTIME READERS:
`core.orchestrator._strategy_context_snapshot_metadata`
`core.runtime_snapshot_producer._strategy_context_from_market_symbol`
`StrategyContext`

PROPAGATION PATH:
`completed_bar_history -> core.session_atr.calculate_session_atr_state -> core.market_data.fetch_live_market_data -> core.orchestrator._strategy_context_snapshot_metadata -> core.runtime_snapshot_producer._strategy_context_from_market_symbol -> StrategyContext`

CONTRACT VERSION:
`atr_short_long_v1`

TRUE-RANGE RESULT:
- First session bar uses `high - low`.
- Later contiguous bars use `max(high - low, abs(high - previous contiguous close), abs(low - previous contiguous close))`.
- The first post-gap bar uses `high - low` and restarts contiguity.

SHORT-WINDOW RESULT:
- `atr_short` is unavailable until 5 consecutive valid true-range observations exist.
- After that it is the rolling mean of the latest 5 contiguous true ranges.

LONG-WINDOW RESULT:
- `atr_long` is unavailable until 30 consecutive valid true-range observations exist.
- After that it is the rolling mean of the latest 30 contiguous true ranges.

SHORT WARM-UP RESULT:
- Strict full-window warm-up is enforced.
- No partial-window estimate is emitted.

LONG WARM-UP RESULT:
- Strict full-window warm-up is enforced.
- No partial-window estimate is emitted.

ROLLING POST-WARM-UP RESULT:
- A 35-bar synthetic completed-bar session produced `atr_short=3.0` and `atr_long=3.0`.
- The same session remained deterministic across repeated calculations.

GAP CONTINUITY RESULT:
- A deterministic intra-session gap reset the contiguous run.
- The first post-gap bar remained a `high - low` true range.
- The 5-bar post-gap state produced `atr_short=3.0` and left `atr_long=None`.

SESSION RESET RESULT:
- Completed-bar history is session-scoped.
- Session boundary resets both windows.
- The replay proof uses completed-bar prefixes from the selected corpus and preserves the session boundary behavior.

MISSING-VALUE RESULT:
- Unavailable ATR fields remain `None`.
- No numeric zero fill is used for unavailable values.
- Long ATR remains missing before the 30-bar window is satisfied.

PROVENANCE RESULT:
- Provenance includes `contract_version`, `source_component`, `source_history_hash`, `calculation_hash`, `timeframe`, `session_date`, `latest_completed_bar_timestamp`, `completed_bar_count`, `current_contiguous_bar_count`, `short_lookback`, `long_lookback`, `short_available`, `long_available`, `continuity_status`, `gap_count`, `latest_gap_timestamp`, and `warnings`.

CAPTURED REPLAY_CORPUS:
- Full-session proof uses `runtime/upstox_candidate_replay/20240530/underlying/NIFTY_20240530.parquet` (`946a1f1ca171e9ef03c08a59bdf6e36b76e1937355afba1765470ca0d16d7606`) and `runtime/upstox_candidate_replay/20240701/underlying/BANKNIFTY_20240701.parquet` (`1ac538c9f7affef416f811a83a1c6fba87fe06745e798aede7f2ea739293cbbc`).
- Partial-session proof uses `runtime/upstox_candidate_replay/20241212/underlying/BANKNIFTY_20241212.parquet` (`529b505f2258e09be12118aa306a1e9aba4eddc5463ffcc95ce6d077c4b33567`), which is the accepted 374-bar partial session.
- Consecutive-session reset coverage uses `runtime/upstox_candidate_replay/20240701/underlying/BANKNIFTY_20240701.parquet` (`1ac538c9f7affef416f811a83a1c6fba87fe06745e798aede7f2ea739293cbbc`) and `runtime/upstox_candidate_replay/20240702/underlying/BANKNIFTY_20240702.parquet` (`ec66c68717cfe7580168a0f48802fefe1ffea29438df4080f9447e900c3ccbff`).
- A synthetic gap fixture in `tests/test_session_atr_runtime.py` proves the strict contiguity reset path.

CHECKPOINT RESULTS:
- After first bar: short missing, long missing.
- After fourth bar: short missing, long missing.
- After fifth bar: short available, long missing.
- After twenty-ninth bar: short available, long missing.
- After thirtieth bar: short available, long available.
- Final bar: both available on full-session rows.

FUTURE-MUTATION PROOF:
- Prefix calculations remain stable when later bars are changed because the calculator uses only the supplied completed-bar history.
- `tests/test_phase3a3_atr_proofs.py::test_future_bar_mutation_cannot_change_earlier_atr_checkpoint` mutates only bars strictly after the cutoff and keeps the entire ATR snapshot unchanged.

TRUNCATION-EQUIVALENCE PROOF:
- `tests/test_phase3a3_atr_proofs.py::test_full_source_cutoff_equals_physically_truncated_prefix` compares a full source session evaluated at cutoff T with a physically truncated prefix ending at T and gets identical ATR state and hashes.
- `calculate_session_atr_state(state)` versus `calculate_session_atr_state(state.completed_bar_history, symbol=..., session_date=..., timeframe=..., source_history_hash=...)` remains the input-representation equivalence proof, not the truncation-equivalence proof.

INCREMENTAL-VERSUS-BATCH PROOF:
- Batch state and iterable replay state match on the same prefix when supplied the same metadata.
- Repeated calls return the same hash for the same history and contract metadata.

RUNTIME-VERSUS-REPLAY PROOF:
- `core.market_data.calculate_session_atr_state is core.session_atr.calculate_session_atr_state`.
- The runtime market-data row, orchestrator metadata, and context adapter all carry the same ATR values.
- The direct-context candidate fingerprint remains unchanged.

CONSUMER IMPACT MATRIX:
| consumer | before atr_short | before atr_long | after atr_short | after atr_long | before result | after result | expected ATR dependency | unexpected change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `compression_breakout_v1` | missing in runtime path | missing in runtime path | available on truthful completed-bar sessions | available on truthful completed-bar sessions | blocked by missing required evidence in runtime-only paths | candidate can reappear only when truthful ATR history exists | `atr_short / atr_long` compression ratio | none in complete direct-context tests |
| `event_volatility_expansion_v1` | missing in runtime path | missing in runtime path | available on truthful completed-bar sessions | available on truthful completed-bar sessions | blocked by missing required evidence in runtime-only paths | candidate can reappear only when truthful ATR history exists | `atr_short / atr_long` expansion ratio | none in complete direct-context tests |
| `core.movement_regime` | missing in runtime path | missing in runtime path | available on truthful completed-bar sessions | available on truthful completed-bar sessions | ATR ratio evidence absent in runtime-only paths | regime evidence now has truthful short/long ATR inputs | short-vs-long volatility regime evidence | none in complete direct-context tests |

EXPECTED BEHAVIOR_CHANGES:
- Runtime market-data rows now expose truthful `atr_short` and `atr_long`.
- Strategy-context metadata now records the same ATR provenance.
- Replays with fewer than 30 contiguous bars still leave long ATR missing.

UNEXPECTED BEHAVIOR_CHANGES:
- None in the focused ATR suite.
- The only full-suite failure is the established missing-kite-access-token baseline.

PHASE 2B BLOCKING RESULT:
- Unchanged. Missing-evidence blocking remains deterministic and fail-closed.

PHASE 3A1 REGRESSION RESULT:
- None. The completed-bar history contract and its tests still pass.

REQUIRED FIXES COMPLETED:
- Restored the committed Phase 3A2 evidence document before continuing Phase 3A3.
- Implemented the narrow canonical `atr_short_long_v1` calculator.
- Propagated runtime ATR truth into market-data output and orchestrator metadata.
- Added replay, runtime, and proof tests for warm-up, gap reset, session reset, future-mutation invariance, truncation equivalence, and consumer impact.
- Updated the Phase 3A2 evidence wording to describe the authoritative runtime contract.

REQUIRED FIXES REMAINING:
- The repository-wide auth-token baseline still fails in the full suite.
- An unrelated `test_restart_recovery` assertion failure also remains in the repository-wide suite.
- The phase commit hash in this document is `12bebbad3e554e97538e762e0d0e8538cecb0b6b`.

FOCUSED TEST RESULT:
- `python -m pytest -q tests/test_atr_contract_decision.py tests/test_session_atr_runtime.py tests/test_captured_atr_replay.py tests/test_phase3a3_atr_proofs.py tests/test_completed_bar_history_contract.py tests/test_captured_market_session_replay.py tests/test_strategy_context_truth.py tests/test_strategy_missing_evidence_policy.py tests/test_strategy_missing_evidence_observability.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
- `135 passed, 1 warning in 111.24s`

ADDITIONAL DISCOVERED TEST RESULT:
- `python -m pytest -q tests/test_captured_atr_replay.py`
- `4 passed, 1 warning in 100.59s`

STATIC CHECK RESULT:
- `python -m py_compile core/session_atr.py core/market_data.py core/orchestrator.py tests/test_atr_contract_decision.py tests/test_session_atr_runtime.py tests/test_captured_atr_replay.py tests/test_phase3a3_atr_proofs.py`
- `ruff check core/session_atr.py tests/test_session_atr_runtime.py tests/test_captured_atr_replay.py tests/test_phase3a3_atr_proofs.py tests/test_atr_contract_decision.py`
- `git diff --check`
- all passed on the owned files

FULL-SUITE RESULT:
- `python -m pytest -q`
- `2 failed, 5791 passed, 1 deselected, 935 warnings in 529.99s`

FIRST FAILURE:
- `tests/test_htf_real_paper_monitor.py::test_restart_recovery`
- `AssertionError: assert 634119278117 == '634119278117'`
- The repository-wide auth-token baseline also fails later in the suite at `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports` with `RuntimeError:[AUTH] missing_kite_access_token`.

NEW ARCHITECTURE:
- None beyond the necessary minimal pure calculator and runtime propagation wiring.

REMAINING RISKS:
- The missing-kite-access-token baseline still blocks a completely green full suite.
- The phase commit hash in this document is `12bebbad3e554e97538e762e0d0e8538cecb0b6b`.

ORIGINAL DIRTY WORKTREE STATUS:
- A tracked evidence file was overwritten by an aborted handback and was restored before phase implementation continued.

ATR-CONTRACT WORKTREE CLEAN STATUS:
- Clean after the required restoration step, before Phase 3A3 implementation began.

PUSH STATUS:
- Not pushed.

NEXT MINIMAL STEP:
Review Phase 3A3 ATR runtime evidence, then build the temporal setup-conformance harness before repairing individual strategies.
