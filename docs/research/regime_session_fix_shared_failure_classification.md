# Regime session fix shared failure classification

Branch:

- `ram/fix-regime-session-context-propagation`

Branch HEAD before any new commit:

- `997db1baf118d5974395cd170ae24ba54384826b`

Current uncommitted files at classification time:

- `core/market_data.py`
- `core/orchestrator.py`
- `tests/test_market_data_warm_seed.py`

## 1. Environment evidence

Commands run on both branch and clean `origin/main` worktree:

```bash
which python
which python3
python --version 2>&1 || true
python3 --version
python3 -m pip --version
python3 -m pip show pytest xgboost 2>/dev/null || true
uname -a
echo "$PATH"
echo "$PYTHONPATH"
```

Observed on both sides:

- `python` does not exist in `PATH`
- `python3` exists and is `Python 3.14.2`
- `pytest` is installed
- `xgboost` is installed
- same macOS / arm64 environment on both sides

Classification:

- `tests/test_strategy_live_shadow.py` subprocess failures are a shared test-infrastructure portability failure because they invoke literal `python` via `subprocess.run([...])` while `python` is absent from `PATH`.
- `tests/test_meta_labeler.py` collection failure is a shared environment / dependency failure because both sides fail during import with the same `xgboost.core.XGBoostError` rooted in missing `libomp.dylib`.

## 2. XGBoost/libomp blocker

Branch command:

```bash
python3 -m pytest -q tests/test_meta_labeler.py -vv --tb=long
```

Branch exit:

- `BRANCH_META_EXIT=2`

Main command:

```bash
cd /tmp/tradebot-vwap-origin-main && python3 -m pytest -q tests/test_meta_labeler.py -vv --tb=long
```

Main exit:

- `MAIN_META_EXIT=2`

Both fail during collection/import with the same root exception:

- `xgboost.core.XGBoostError`
- native library load failure for `libxgboost.dylib`
- missing `@rpath/libomp.dylib`

Classification:

- `SHARED_ENVIRONMENT_FAILURE`

## 3. Strategy live shadow failures

Branch command:

```bash
python3 -m pytest -q tests/test_strategy_live_shadow.py -vv --tb=long
```

Branch failures:

- `tests/test_strategy_live_shadow.py::test_shadow_missing_option_chain_contract`
- `tests/test_strategy_live_shadow.py::test_shadow_missing_quote`
- `tests/test_strategy_live_shadow.py::test_shadow_stale_quote`
- `tests/test_strategy_live_shadow.py::test_shadow_wide_spread`
- `tests/test_strategy_live_shadow.py::test_shadow_bad_quote`
- `tests/test_strategy_live_shadow.py::test_fixture_mode_still_rejected_by_analyzer`
- `tests/test_strategy_live_shadow.py::test_shadow_valid_execution`

Main command:

```bash
cd /tmp/tradebot-vwap-origin-main && python3 -m pytest -q tests/test_strategy_live_shadow.py -vv --tb=long
```

Main failures:

- same seven node IDs

Exact subprocess command attempted by the tests:

```python
[
    "python", "scripts/run_strategy_live_shadow.py",
    ...
]
```

Observed exception:

- `FileNotFoundError: [Errno 2] No such file or directory: 'python'`

This is identical on both branch and `origin/main`.

Classification:

- `SHARED_TEST_INFRASTRUCTURE_PORTABILITY_FAILURE`

## 4. Orchestrator report failure

Branch command:

```bash
python3 -m pytest -q tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports -vv --tb=long -s
```

Branch outcome:

- assertion failure
- `engine_cycle_status["last_error"] == "RuntimeError:kite_api_key_missing"`

Main command:

```bash
cd /tmp/tradebot-vwap-origin-main && python3 -m pytest -q tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports -vv --tb=long -s
```

Main outcome:

- same assertion failure
- same `last_error`

Repeat runs on branch:

- 3 / 3 identical failures
- no flakiness observed
- no order dependence observed in the isolated reruns

Observed shared failure node:

- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

Classification:

- `SHARED_PRE_EXISTING_REPO_FAILURE`

Reason:

- failure is identical on branch and `origin/main`
- root cause is the repository's current runtime behavior under missing kite credentials, not the session fix patch
- it is deterministic in isolated reruns

## 5. Supplemental suite results

Branch command:

```bash
PYTHONHASHSEED=0 python3 -m pytest -q tests/ --ignore=tests/test_meta_labeler.py --tb=short
```

Branch exit:

- `BRANCH_SUPPLEMENTAL_EXIT=1`

Branch failures:

- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- `tests/test_strategy_live_shadow.py::test_shadow_missing_option_chain_contract`
- `tests/test_strategy_live_shadow.py::test_shadow_missing_quote`
- `tests/test_strategy_live_shadow.py::test_shadow_stale_quote`
- `tests/test_strategy_live_shadow.py::test_shadow_wide_spread`
- `tests/test_strategy_live_shadow.py::test_shadow_bad_quote`
- `tests/test_strategy_live_shadow.py::test_fixture_mode_still_rejected_by_analyzer`
- `tests/test_strategy_live_shadow.py::test_shadow_valid_execution`

Main command:

```bash
PYTHONHASHSEED=0 python3 -m pytest -q tests/ --ignore=tests/test_meta_labeler.py --tb=short
```

Main exit:

- `MAIN_SUPPLEMENTAL_EXIT=1`

Main failures:

- same eight node IDs

Comparison summary:

- failures only on branch: none
- failures only on `origin/main`: none
- failures on both: the eight node IDs listed above
- same node ID but different exception: none observed
- collection blockers shared by both: `tests/test_meta_labeler.py`
- failures that disappear in isolated reruns: none observed
- failures that depend on execution order: none observed

## 6. Affected suite recheck

After the `regime_ts` and `_is_regime_unstable_hint()` fixes, the focused affected suites passed locally except for the known shared blockers.

Relevant passing commands:

```bash
pytest -q tests/test_market_data_warm_seed.py tests/test_breakout_entropy_override.py tests/test_dashboard_live_suggestions.py tests/test_entropy.py tests/test_entropy_contract.py tests/test_decision_dag.py tests/test_gate_status_log.py --tb=short
```

Result:

- `114 passed`

And:

```bash
pytest -q tests/test_orchestrator_strategy_gate_once.py tests/test_jit_quote_revalidation.py tests/test_stale_indicator_blocker_strategy_gate.py --tb=short
```

Result:

- `15 passed`

## 7. July 9 replay proof

Replay evidence from the post-fix July 9 Upstox capture remained unchanged for the session-context correction:

- `current_runtime_events_using_DEFAULT = 0`
- `session_context_mismatch_count = 0`
- `false_high_entropy_count = 0`
- `false_pass_count = 0`
- `consumer_gate_divergence_count = 0`
- `genuine_high_entropy_count_after_correction = 1050`

Probability / entropy invariance:

- probability vectors unchanged
- raw entropy unchanged
- normalized entropy unchanged
- primary regimes unchanged

## 8. Classification summary

- `tests/test_meta_labeler.py` -> `SHARED_ENVIRONMENT_FAILURE`
- `tests/test_strategy_live_shadow.py` -> `SHARED_TEST_INFRASTRUCTURE_PORTABILITY_FAILURE`
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports` -> `SHARED_PRE_EXISTING_REPO_FAILURE`
- remaining branch-only session-context regressions -> fixed

## 9. Final verdict at classification time

- `PASS_SESSION_FIX_REGRESSION_CLEAN_WITH_SHARED_BLOCKERS`
