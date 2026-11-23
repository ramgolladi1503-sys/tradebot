# PR #987 R3 Targeted Remediation

## Verdict: HOLD

The two frozen blockers have targeted code corrections and independent test evidence, but the worktree is not review-ready. CodeRabbit found additional WAL risks: constructor failure after worker start, a forked child blocked on an inherited mutex, sidecar namespace collision that can admit two owners, and missing parent-directory durability when the WAL directory is created. It also found a `PULLBACK_WAIT` recovery path that can enter a new leg without proof of the completed prior leg. The full `test_sentinel_advisor_hardening_003.py` suite still has 18 failures, and the smoke harness's expected `IN_FLIGHT` outcome remains blocked by synthetic, untrusted OR evidence. Finally, the deployment process and its WAL filesystem could not be identified, so the external-volume test does not prove the deployed filesystem's locking semantics.

No strategy, threshold, broker, order, credentials, live configuration, or running process was changed. No commit, push, merge, or deployment occurred. Tests and source investigations made no broker API or trading HTTP requests. CodeRabbit used its authenticated review service for the requested code reviews.

## Work item and scope

- Work item: PR #987, R3 targeted remediation (`BUG` / WAL ownership and session rollover).
- Baseline and worktree `HEAD`: `94ab77b554d7540adee68746d8b5016e92ff7d34`.
- Branch: `ram/pr987-egm-remediation`.
- Human request explicitly authorized the two R3 corrections and tests; the request prohibited broker activity, commits, pushes, merges, and deployment.
- No canonical Epic/Feature ID or durable TradeBot work-item record was supplied or linked. Permanent task-platform intake is therefore `UNSATISFIED`; this report does not claim the repository lifecycle was completed or acceptance was granted.

## Latest R3 ownership follow-up patch inventory

| Path | Status | Purpose | SHA-256 before R3 edit | SHA-256 after R3 edit |
|---|---|---|---|---|
| `core/active_position_manager.py` | modified | Serialize owner check with persistence and close; reject stale queued writer | `26628ce29b5cd44fc1de4707f5383d1b2291ae0111ffceac8527a1b42b98ad6f` | `77faf41dc548ac7f90963390ad6c9eebef2e61ecbb80dc2365fba5ed3bb02771` |
| `scripts/run_premarket_firing_smoketest.py` | modified | Close advisor APM owners before temporary WAL cleanup; preserve stable sidecars | `e6311a2ae960321f20ba303e4300163b427d9e46e50cd3013a6db74cb54f11d7` | `2c171a612da43310f50cf4b969cfa488d840a3ea2183dadea9564154fdd19447` |
| `tests/unit/test_apm_wal_process_ownership.py` | untracked/new | Deterministic close/write race and process ownership regressions | `600fdac478023e612ed86308242c06f5d8f7c6847799b99a5333fa71879b677d` | `78f37d30987a778e69e28b1cb6d5ff16cf68451949f7c248091e5c617f5e2953` |
| `tests/unit/test_sentinel_premarket_and_sizing_hardening.py` | modified | Repeat and exception teardown regressions; retain original trade assertions | `512a4c270709527974a35c710973b3efb74443d04f9559f129adb1d18666e129` | `5074fd87a63c7c58dd7d528ad9a10511cd97e188154934a534c19fb76593c3bc` |

The rollover correction and shutdown wiring were applied in the earlier R3 pass and remained unchanged during this final ownership follow-up. The remaining rows are other PR #987 changes included in the CodeRabbit directory reviews. This separates the latest four-file delta from the combined R3 and earlier PR work:

| Path | Status | SHA-256 at review |
|---|---|---|
| `core/sentinel_live_stream_advisor.py` | modified; contains earlier R3 reachable rollover reset plus earlier PR work; unchanged during final ownership follow-up | `6fde00d9f9c0e5db4eb0000a9ebc19e9d981294b50d5b24f5bd794b186540c3b` |
| `core/reconciliation/__init__.py` | untracked | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `scripts/upstox_daily_live_capture_and_stitch.py` | modified; earlier R3 shutdown wiring plus earlier PR work; unchanged during final ownership follow-up | `fbd9ec4521b193da899bef1cbcea5a75df38d57a6f5324d070d784c42c9e90be` |
| `tests/unit/test_apm_runner_trailing_regression.py` | untracked | `c64cb8537148570a8ae6eee52ed339164a37578a0bbaa9b59f38462a80b864a7` |
| `tests/unit/test_pr987_r2_controlled_remediation.py` | untracked | `57685a6c973c93022d1fe4d539d2343d27d3467af1a71ea1857b1554b7326110` |
| `tests/unit/test_sentinel_advisor_hardening_003.py` | modified; includes rollover regression and earlier PR tests; unchanged during final ownership follow-up | `0c385f8ba3da489ef2827834dfce9303a69fc9e982ad47e0fc25671dffccebe2` |
| `tests/unit/test_sentinel_optionmate_execution_hardening.py` | modified from earlier PR work | `a9e78d982999c06c8b7bd1e51e29aac52f58839bd3b979477b653fd2e762294b` |
| `tests/unit/test_sentinel_optionmate_rbfn_auction.py` | modified from earlier PR work | `633f3f9f0b4071cb1933c5b770dbdc7f2ff81f6efdf50eb5bddf79cb8741a245` |
| `tests/unit/test_sentinel_rbfn_scenarios_s2_s4_s7.py` | modified from earlier PR work | `47cd858a6db1a3a197b500f4b84c02bc32f67b7db6036897f7a5f3bb9facb977` |

Scoped `git status` verified the 13 paths in these two tables. Generated files under `runtime/`, older untracked evidence documents, and preflight snapshots are not source/test inputs to this remediation and were not included in CodeRabbit review. A whole-worktree status listing has previously stalled on the external volume; no claim is made that every unrelated artifact was inventoried here.

## P0-A — NIFTY session rollover

### Reproduction before the correction

The frozen regression `test_india_local_date_transition_resets_only_current_index_opening_range` failed: OR evidence/bounds reset for the next session, but the legacy NIFTY `active_range_high` remained `24050` instead of `-inf`. The assignments intended to clear the scalar range were unreachable in the old control flow.

### Correction and evidence

The reset assignments were moved into the reachable per-index rollover helper. NIFTY rollover now resets `active_range_high` and `active_range_low` together with the NIFTY OR evidence; same-session observations do not reset them. SENSEX and BANKNIFTY continue to use the same rollover helper, but do not clear the NIFTY-only scalar range.

Independent QA recorded the rollover group as **4/4 passing**, including NIFTY rollover, stale active-range removal, same-session no-reset, and other-index isolation. The advisor source hash `6fde00d9…186540c3b` remained unchanged during the final WAL lifecycle follow-up; the P0-A reset is part of the earlier R3 changes in that file.

## P0-B — Cross-process WAL ownership

### Reproduction before the correction

The pre-fix two-process harness reported both writers successful and both reached the barrier; the resulting JSON was valid but `daily_trade_count` was `1`, proving one update was lost. The frozen verification report independently identified the missing cross-process owner lock.

### Correction and evidence

The APM opens a stable `<resolved WAL path>.lock` sidecar and takes nonblocking exclusive `flock` ownership before recovery or entry admission. The sidecar is not replaced with the WAL and is not unlinked on close. A second owner fails with `WALOwnershipError` before recovery. Persistence now takes `_wal_lock` and rechecks ownership inside that lock, so a queued old writer either completes before close or is rejected after close; it cannot write after a successor acquires the WAL. Normal advisor shutdown closes its per-index managers; process death releases the OS lock.

The deterministic stale-writer test pauses a writer at local-lock acquisition, closes its manager, opens a successor, and then releases the stale writer. It asserts `WALOwnershipError` and unchanged WAL bytes. Other tests cover simultaneous startup, a blocked second owner, clean release, abnormal process death/recovery, fork ownership guards, constructor partial startup, and sidecar identity.

Independent QA ran all **8 WAL ownership tests** on `/Volumes/TradeBotFast` and all passed. `diskutil` identifies that volume as APFS on an external removable disk image. This proves behavior on that mounted volume in the test environment only. The supplied process IDs `54383` and `54153` were absent when checked, and the deployed process working directory/WAL mount could not be established. Deployment-filesystem compatibility remains `UNRESOLVED`.

### Smoke harness teardown

The premarket harness now calls `shutdown_apm_wal_ownership()` in `finally`, before deleting temporary JSON WALs. Persistent `.lock` sidecars are retained. If lock shutdown reports errors, WAL payloads are preserved and a successful primary flow is converted to an explicit failure; an earlier primary exception is logged and preserved.

The smoke harness's original synthetic signal still fails closed because its OR evidence is `SYNTHETIC_REPLAY_SEED`, while the production validator requires trusted exact 30-bar OR provenance. The existing `IN_FLIGHT` assertions were not weakened. A new same-process repeat test expects the same specific pre-existing `IN_FLIGHT` assertion failure twice, verifies sidecar identity, and reacquires the WAL after each call. This verifies teardown only; it is not a successful trade smoke test.

## Verification

Environment: `/opt/anaconda3/bin/python` 3.12, macOS; invocations used `python -S`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONDONTWRITEBYTECODE=1`, no Upstox token, and isolated basetemp under `/Volumes/TradeBotFast/.pr987-r3-tests`. Two pandas dependency-version warnings were reported (`numexpr` and `bottleneck`).

### Combined requested regression batch

Exit code **0** — **301 passed**, two dependency warnings, 30.50s. It includes 21 focused APM tests, 19 controlled-remediation tests, 8 WAL ownership tests, 3 lifecycle teardown tests, the 250 historical selectors, and the other listed Sentinel regressions. Exact command:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r3-final-home TMPDIR=/Volumes/TradeBotFast/.pr987-r3-tests PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -S -c 'import sys; sys.path.insert(0, "/Volumes/TradeBotFast/worktrees/pr987-egm-remediation"); sys.path.append("/opt/anaconda3/lib/python3.12/site-packages"); import pytest; raise SystemExit(pytest.main(["-p", "no:cacheprovider", "--basetemp=/Volumes/TradeBotFast/.pr987-r3-tests/final", "-q", "tests/unit/test_apm_runner_trailing_regression.py", "tests/unit/test_pr987_r2_controlled_remediation.py", "tests/unit/test_apm_wal_process_ownership.py", "tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_repeated_calls_release_wal_ownership_and_keep_sidecars", "tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_reports_shutdown_failure_without_masking_existing_error", "tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_exception_path_releases_wal_ownership", "tests/unit/test_sentinel_realtime_journal.py", "tests/unit/test_sentinel_regime_router.py", "tests/unit/test_sentinel_rbfn_scenarios_s2_s4_s7.py", "tests/unit/test_sentinel_optionmate_execution_hardening.py", "tests/unit/test_sentinel_advisor_hardening_005.py", "tests/unit/test_sentinel_optionmate_rbfn_auction.py", "tests/unit/test_sentinel_advisor_hardening_003.py::test_mode5_bar_abstains_before_history_mutation_without_valid_or"]))'
```

### Full hardening003 suite and baseline comparison

- Remediation source: **18 failed, 51 passed**, exit 1; 10.87s.
- Baseline source at `94ab77b554d7540adee68746d8b5016e92ff7d34`, with the same test file and the untracked reconciliation import helper overlaid for test collection: **19 failed, 50 passed**, exit 1; 3.75s.
- All 18 failures below match between remediation and baseline. The baseline-only failure `test_mode5_bar_abstains_before_history_mutation_without_valid_or` passes on the remediation. No new failure was identified. This is not a full-suite pass.

Exact remediation command:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r3-full003-home TMPDIR=/Volumes/TradeBotFast/.pr987-r3-tests PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -S -c 'import sys; sys.path.insert(0, "/Volumes/TradeBotFast/worktrees/pr987-egm-remediation"); sys.path.append("/opt/anaconda3/lib/python3.12/site-packages"); import pytest; raise SystemExit(pytest.main(["-p", "no:cacheprovider", "--basetemp=/Volumes/TradeBotFast/.pr987-r3-tests/full003-final", "-q", "tests/unit/test_sentinel_advisor_hardening_003.py"]))'
```

Exact baseline command (the baseline source tree was made with `git archive`; the current test file and the current untracked `core/reconciliation` import helper were copied into that isolated tree, with their hashes checked):

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r3-base003-home TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -S -c 'import sys; sys.path.insert(0, "/private/tmp/pr987-baseline-source-94ab77b"); sys.path.append("/opt/anaconda3/lib/python3.12/site-packages"); import pytest; raise SystemExit(pytest.main(["-p", "no:cacheprovider", "--basetemp=/private/tmp/pr987-r3-base003-retry", "-q", "/private/tmp/pr987-baseline-source-94ab77b/tests/unit/test_sentinel_advisor_hardening_003.py"]))'
```

Matching failure node IDs:

```text
test_rejected_bar_candidates_preserve_state[duplicate_timestamp_epoch]
test_rejected_bar_candidates_preserve_state[same_epoch_later_timestamp]
test_rejected_bar_candidates_preserve_state[decreasing_timestamp_epoch]
test_rejected_bar_candidates_preserve_state[prior_session]
test_future_clock_skew_exact_bound_and_just_over_rejected_before_mutation
test_completed_bar_epoch_and_next_ist_boundary_contract
test_symbolic_key_underlying_mismatch_vetoes_before_dispatch[NIFTY 25400 CE-NSE_FO|BANKNIFTY_52000_PE]
test_symbolic_key_underlying_mismatch_vetoes_before_dispatch[BANKNIFTY 52000 PE-NSE_FO|NIFTY26NOV24150CE]
test_symbolic_key_underlying_mismatch_vetoes_before_dispatch[SENSEX 81400 CE-BSE_FO|NIFTY26NOV24150CE]
test_invalid_instrument_key_vetoes_before_entry_or_exit_dispatch[STANDBY]
test_invalid_instrument_key_vetoes_before_entry_or_exit_dispatch[IN_FLIGHT]
test_invalid_instrument_key_vetoes_before_entry_or_exit_dispatch[EXIT_PENDING]
test_gate_sentinel_09_zero_timestamp_eviction
test_mode5_or_v2_seed_requires_exact_aware_same_session_coverage
test_mode5_or_recheck_blocks_apm_after_session_rollover
test_mode5_dispatch_occurs_after_advisor_lock_is_released
test_mode5_depth_gate_checks_companion_or_before_dispatch[OPENING_DRIVE]
test_mode5_depth_gate_checks_companion_or_before_dispatch[CONTINUOUS_STATE_MACHINE]
```

### Existing premarket harness suite

Exit code **1** — **4 failed, 11 passed** on the remediation and the same four failures reproduced against baseline source. The four include three old smoke tests that expect `STATE_IN_FLIGHT` but receive `STATE_STANDBY`, plus the OTM expansion case. The direct SM01–SM04 selector run was **3 failed, 1 passed** (SM02 passed); the other three failed at the unchanged `Expected APM state IN_FLIGHT, got STANDBY` assertion. These failures are retained and are not represented as R3 regressions or successful trade behavior.

### Independent focused lifecycle rerun

On a separate byte/hash-verified local mirror, Technical & Quant Analyst ran the deterministic stale-writer test and the repeat/exception smoke teardown tests: **3 passed**, exit 0, two pandas warnings. This is local temporary filesystem evidence, not deployment-volume evidence.

`git diff --check` passed. No source hash changed during independent QA. No broad repository test pass is claimed.

## Remaining blockers and limits

1. **WAL ownership namespace collision:** CodeRabbit independently reproduced two managers owning the same logical WAL when one WAL path equals another manager's `.lock` sidecar path. This can bypass the new exclusive ownership contract.
2. **WAL lifecycle failures:** a later advisor-constructor exception can leak the worker and all acquired APM locks; a forked child can block in `close()` on an inherited mutex. Both were independently reproduced.
3. **WAL directory durability:** when the WAL parent directory is newly created, the forced write syncs the WAL and that directory but not the parent entry recording the new directory. This conditional power-loss case has no simulated crash proof and remains unverified.
4. **Deployment filesystem not identified:** the actual live processes were absent and their current WAL path/mount was not observable. External APFS test results cannot certify another filesystem or mount configuration.
5. **Recovery integrity:** CodeRabbit reproduced recovery of `PULLBACK_WAIT` as durable without matching completed-leg history, allowing a later re-entry without proof of the prior leg.
6. **Path aliases:** path resolution unifies symlink aliases but does not establish ownership for hard-link aliases. The supported WAL path invariant needs documentation or an enforceable path-identity policy.
7. **Full Sentinel suite:** hardening003 still has 18 matching baseline failures. A selected batch passing 301 tests does not establish full suite success.
8. **Synthetic trade smoke remains blocked:** fail-closed OR provenance rejects the harness's synthetic seed. No change to that production gate was made.
9. **Other CodeRabbit findings:** epoch contiguity, entry journal/counter ordering, OR queue shutdown admission, cooldown recovery classification, replay-only synthetic evidence, and test assertion/hygiene findings are detailed in [the CodeRabbit comparison report](PR987_CODERABBIT_INDEPENDENT_REVIEW.md). Several are valid and outside the narrow two-blocker correction.
10. **Fill authority:** APM state and WAL transitions remain advisory. There is no authoritative fill source in this scope; nothing here proves a broker fill or realized P&L.
11. **Delivery gates:** no canonical Epic/Feature linkage or durable work-item intake was available. No merge/release/deployment approval is claimed.

## Role and evidence handoff

- Business Analyst: initial R3 scope/acceptance output was retained; no strategy or live-operation scope was added.
- Product Owner: post-development outcome `REJECTED` (`/root/r3_product_owner`); deployment filesystem, new WAL lifecycle blockers, existing suite failures, and absent durable work-item linkage prevent acceptance.
- Grill Me: revised review blocked on the later constructor-failure and forked-mutex lifecycle risks; specific sequence and required tests recorded in the review thread.
- Hermes: approved the narrow ownership linearization and offline smoke teardown contract; accepted an expected fail-closed harness assertion as teardown evidence only.
- GSD: implemented the four-file R3 correction and tests; did not alter trade assertions or OR provenance.
- QA: `PASS` for scoped R3 behavior; full hardening003 and premarket suite failures remain as above.
- Technical & Quant Analyst: rollover/close-race/smoke cleanup evidence verified; deployment filesystem and residual alias assumptions remain unresolved; CodeRabbit Major findings separately challenged.
- Senior QA: source/implementation outcome `BLOCK` on the constructor and inherited-mutex findings; a later documentation/hash consistency check returned `PASS` for report accuracy only and does not close the code blockers.
- UAT: `PASS` for report clarity and factual corrections; this does not establish technical readiness or product acceptance.
- Product acceptance remains `REJECTED`; this report remains **HOLD** pending resolution of code, filesystem, regression, and delivery-record blockers.

## Rollout notes

- New config keys: none.
- Tests added: 1 deterministic WAL ownership test; 3 smoke teardown/error tests. Existing assertions were retained.
- Rollout: no deployment performed. Before any future rollout, resolve the remaining ownership defects, verify the actual deployment WAL mount semantics, rerun the required full suite, and obtain the repository's independent QA, Senior QA, UAT, product acceptance, and release gates.
- Rollback: keep this patch unmerged/unreleased. No live process, deployment, broker, or order state was changed; tests may have created local temporary/runtime artifacts.
