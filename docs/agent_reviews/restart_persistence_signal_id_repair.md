# Restart Persistence `signal_id` Repair

IMPLEMENTATION DIRECTION:
RIGHT

APPROVED OBJECTIVE:
Preserve `signal_id` as an exact string across CSV restart persistence without changing strategy, ranking, ATR, or execution behavior.

WHAT WAS ACTUALLY IMPLEMENTED:
`RealPaperMonitor._load_existing_log` now reads `signal_id` with an explicit pandas string dtype so digit-only identifiers and leading-zero identifiers reload as strings instead of being inferred as integers. Focused regression tests now cover digit-only, leading-zero, non-digit, missing-value, and legacy CSV cases through the real save/load path.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

VERDICT:
RESTART_PERSISTENCE_COMPLETE

BASE COMMIT:
`272b80774a0d0afed951783d2eddc40d81e61494`

STARTING HEAD:
`272b80774a0d0afed951783d2eddc40d81e61494`

FINAL HEAD:
pending commit in this task

BRANCH:
`fix/restart-persistence-signal-id`

WORKTREE:
`/Users/madhuram/tradebot-restart-persistence`

ROOT CAUSE:
pandas CSV dtype inference in `RealPaperMonitor._load_existing_log`

FILES CHANGED:
- `scripts/run_htf_real_paper_monitor.py`
- `tests/test_htf_real_paper_monitor.py`

IMPLEMENTATION:
- `RealPaperMonitor._load_existing_log` now calls `pd.read_csv(..., dtype={"signal_id": "string"})`.
- The rest of the persisted schema remains untouched.
- `signal_id` continues to be treated as an opaque identifier, not a numeric field.

CONTRACT IMPLEMENTED:
- Present identifier reloads as `str`.
- Leading zeros are preserved.
- Missing values remain missing and do not become fabricated strings.
- Legacy CSV files containing unquoted digit-only identifiers reload as strings.
- Unrelated numeric columns remain numeric.

DIGIT-ONLY RESULT:
- input: `"634119278117"`
- loaded value: `"634119278117"`
- loaded type: `str`

LEADING-ZERO RESULT:
- input: `"000634119278117"`
- loaded value: `"000634119278117"`
- loaded type: `str`

NON-DIGIT RESULT:
- input: `"signal-634119278117"`
- loaded value: `"signal-634119278117"`
- loaded type: `str`

MISSING-VALUE RESULT:
- input: `None`
- loaded value: `None`
- loaded type: `NoneType`
- no fabricated `"nan"`, `"None"`, or `"<NA>"` string

LEGACY-CSV RESULT:
- a CSV containing an unquoted digit-only `signal_id` reloads as the exact string identifier
- legacy numeric-looking identifiers remain strings after restart

NUMERIC-COLUMN CONTROL:
- `risk` remains numeric
- `nifty_spot` remains numeric

TARGETED TEST RESULT:
- `python -m pytest -q tests/test_htf_real_paper_monitor.py`
- `10 passed in 2.06s`

FOCUSED TEST RESULT:
- `python -m pytest -q -k "real_paper_monitor or restart_recovery or signal_id or paper_log"`
- `12 passed, 5788 deselected in 33.40s`

ORCHESTRATOR REGRESSION SLICES:
- `python -m pytest -q tests/test_orchestrator_reports_finally.py`
- `1 failed in 8.10s`
- failure classification: `ENVIRONMENT_CREDENTIAL`
- failing assertion still points at the known missing token path, not this repair

FULL-SUITE RESULT:
- `python -m pytest -q`
- `1 failed, 5798 passed, 1 deselected, 935 warnings in 484.76s`
- failure classification: `ENVIRONMENT_CREDENTIAL`
- first failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- failure cause: `RuntimeError:[AUTH] missing_kite_access_token`

FULL SUITE RERUN IN THIS TASK:
NO

LATEST APPLICABLE FULL-SUITE RESULT:
`1 failed, 5798 passed, 1 deselected, 935 warnings in 484.76s`
STATIC CHECK RESULT:
- `python -m py_compile scripts/run_htf_real_paper_monitor.py tests/test_htf_real_paper_monitor.py`
- `ruff check scripts/run_htf_real_paper_monitor.py tests/test_htf_real_paper_monitor.py`
- `git diff --check`
- all passed

GENERATED-FILE RECONCILIATION:
- controlled generated spillover from `cfg.EXECUTION_INTENTS_LOG_PATH` appeared as three mock-named files during the full suite
- those files were removed after proof
- `runtime/strategy_validation/regime_timeline.jsonl` was restored to HEAD

CLAIM BOUNDARY:
- this repair does not change ATR, strategy formulas, ranking, execution policy, or restart semantics outside the CSV type boundary
- this repair does not fix the repository-wide auth-token baseline
- this repair does not claim live readiness or profitability

NOT PROVEN:
- strategy correctness
- ATR quality
- profitability
- live execution readiness
- the full-suite auth baseline

NEXT MINIMAL STEP:
Keep the restart-persistence contract in place and merge only this narrow persistence fix.
