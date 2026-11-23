# PR987 Round 2 Controlled Remediation — Red/Green Evidence

## Source identity

- Repository: `/Volumes/TradeBotFast/worktrees/pr987-egm-remediation`
- Baseline HEAD: `94ab77b554d7540adee68746d8b5016e92ff7d34`
- Branch: `ram/pr987-egm-remediation`
- Source remains uncommitted. The final SHA-256 values are recorded in `PR987_R2_FINAL_REMEDIATION_VERDICT.md`.
- Tests ran offline in a clean environment using local fake HTTP clients, temporary directories, and no real token, broker, network, order, or LIVE endpoint.

## Pre-fix reproductions

The first red batch contained exactly two new contract tests and ran against the unchanged target source:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-red-home XDG_CONFIG_HOME=/tmp/pr987-r2-red-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-red-basetemp -q tests/unit/test_pr987_r2_controlled_remediation.py
```

Observed before implementation: `2 failed in 3.30s`.

- Replay with an injected fake client produced three `.get()` calls. No real network was contacted.
- `seed_opening_range_evidence(..., source="UPSTOX_V2_1M_EXACT_30")` forged complete metadata that `_validate_mode5_or_pair` accepted as valid.

The prior independent audit, based on the same pinned source identity, also recorded the genuine streaming call path and its deterministic blocked-request observation. That audit was not re-executed here; it is cited as prior evidence in [PR987_EGM_ROUND2_FINAL_AUDIT.md](/Users/madhuram/tradebot/docs/agent_reviews/PR987_EGM_ROUND2_FINAL_AUDIT.md): `self_lock_owned_inside_http=True`, `tick_b_blocked_during_http=True`, and `tick_b_elapsed_seconds=0.3192`. The present real-path tests replace that failing behavior.

## Post-fix focused evidence

The final focused module, including replay isolation, provenance, both real `on_tick` reconciliation routes, stale rollover and shutdown responses, dedupe, 1–4 lot CE/PE target projection, duplicate targets, WAL write/flush/fsync/replace/directory-sync failures, corrupt/interrupted recovery, entry rejection, trade-history append failure and idempotent advisory liquidation, passed as part of the final regression command below.

The three HTTP concurrency checks were also run independently:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-test-home XDG_CONFIG_HOME=/tmp/pr987-r2-test-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-concurrency-basetemp -q tests/unit/test_pr987_r2_controlled_remediation.py::test_post_open_reconciliation_worker_does_not_hold_stream_lock tests/unit/test_pr987_r2_controlled_remediation.py::test_on_tick_five_minute_close_uses_nonblocking_reconciliation_worker tests/unit/test_pr987_r2_controlled_remediation.py::test_stale_or_response_after_session_rollover_is_discarded
```

Observed: `3 passed in 0.93s`. In each held-request case, the mock observed the worker thread did not own the advisor stream lock; a second tick returned in under 0.2 seconds before the request was released. A separate test covers discarding a valid delayed response after worker shutdown.

## Final regression command

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-test-home XDG_CONFIG_HOME=/tmp/pr987-r2-test-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-final4-basetemp -q tests/unit/test_apm_runner_trailing_regression.py tests/unit/test_sentinel_realtime_journal.py tests/unit/test_sentinel_regime_router.py tests/unit/test_sentinel_rbfn_scenarios_s2_s4_s7.py tests/unit/test_sentinel_optionmate_execution_hardening.py tests/unit/test_sentinel_advisor_hardening_005.py tests/unit/test_sentinel_optionmate_rbfn_auction.py tests/unit/test_pr987_r2_controlled_remediation.py tests/unit/test_sentinel_advisor_hardening_003.py::test_mode5_bar_abstains_before_history_mutation_without_valid_or
```

This is the original seven reported suites plus the new focused contract module and one existing history-boundary test. Observed: `274 passed in 17.57s`, no failures and no skips. The environment emitted two dependency-version warnings: installed `numexpr` is `2.8.7` (pandas asks for `2.10.2` or newer), and installed `bottleneck` is `1.3.7` (pandas asks for `1.4.2` or newer). These warnings did not affect the test result.

## P2 history boundary

Raw observed bars are retained in `bars_5m_history`. Only bars that pass ground-truth and OR validation are added to `bars_5m_strategy_history`, which is the sole source for strategy pattern/range lookbacks. The invalid-OR test now uses the trace writer's queue join barrier and asserts raw observation plus empty strategy history. A late-OR test proves rejected historical bars remain excluded while a later validated bar enters strategy history. Existing pattern fixtures were migrated to the strategy-history collection without changing their OHLC values or expected market paths.
