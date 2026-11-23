# PR987 R2 Addendum — Terminal WAL Recovery and Atomic Liquidation

## Scope and identity

- Worktree: `/Volumes/TradeBotFast/worktrees/pr987-egm-remediation`
- Baseline HEAD remains `94ab77b554d7540adee68746d8b5016e92ff7d34`.
- This is a narrow follow-on for the confirmed liquidation two-write crash gap. Earlier evidence was preserved; no prior report was overwritten.
- Only `core/active_position_manager.py`, the existing untracked focused APM test file, and this addendum were touched during this pass.
- No strategy/risk levels, broker/order/live code, credentials, PR state, or deployment paths were touched.

## Pre-fix red evidence

Exact command:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-wal-home XDG_CONFIG_HOME=/tmp/pr987-r2-wal-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-terminal-red -q tests/unit/test_apm_runner_trailing_regression.py::test_recovery_with_terminal_state_and_position_payload_blocks_entry tests/unit/test_apm_runner_trailing_regression.py::test_successful_liquidation_persists_terminal_state_and_empty_payload_once
```

Observed against the pre-patch source: `3 failed, 1 passed in 3.98s`.

- Recovered `COOL_OFF` and `LIQUIDATED` WAL images with a non-null payload were accepted as those states rather than `RECOVERY_BLOCKED`.
- Liquidation emitted two writes: first `LIQUIDATED` with a non-null position payload, then a second write with the payload cleared.
- The pre-existing `STANDBY` plus payload guard already passed; the added check now covers all terminal/flat states.

## Patch behavior

Recovery now treats `STANDBY`, `COOL_OFF`, and `LIQUIDATED` paired with any non-null payload as inconsistent and fail-closed. It preserves the readable payload in `RECOVERY_BLOCKED`, where `arm_and_enter` rejects new admission.

Successful liquidation now constructs one coherent final snapshot: terminal state, `payload=None`, completed-trade summary and history. That snapshot is force-persisted before success is returned. On any persist/write/fsync failure the current manager remains `RECOVERY_BLOCKED`, restores its in-memory position payload as uncertain, and raises instead of reporting successful liquidation.

Failure-window tests cover `os.replace` failure before replacement (old `EXIT_PENDING` WAL reloads as blocked) and parent-directory fsync failure after replacement (current process remains blocked; the on-disk image is coherent, either the terminal/payload-free replacement or prior active image). Duplicate liquidation remains idempotent and does not append duplicate history.

## Post-fix evidence

Focused terminal-state and crash-window tests:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-wal-home XDG_CONFIG_HOME=/tmp/pr987-r2-wal-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-terminal-green2 -q tests/unit/test_apm_runner_trailing_regression.py::test_recovery_with_terminal_state_and_position_payload_blocks_entry tests/unit/test_apm_runner_trailing_regression.py::test_successful_liquidation_persists_terminal_state_and_empty_payload_once tests/unit/test_apm_runner_trailing_regression.py::test_liquidation_replace_failure_keeps_old_active_wal_and_blocks_recovery tests/unit/test_apm_runner_trailing_regression.py::test_liquidation_post_replace_directory_fsync_failure_blocks_current_manager
```

Observed: `6 passed in 9.09s` (three parameter cases for terminal-state recovery plus three liquidation tests).

APM runner and controlled-remediation suites:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-wal-home XDG_CONFIG_HOME=/tmp/pr987-r2-wal-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-apm-final -q tests/unit/test_apm_runner_trailing_regression.py tests/unit/test_pr987_r2_controlled_remediation.py
```

Observed: `31 passed in 2.25s`. The environment emitted two pandas dependency warnings (`numexpr` and `bottleneck` below pandas recommendations); there were no skips. No live, broker, order, or network calls were made.

`git diff --check` passed for the two scoped source/test files. No full seven-suite regression rerun was attempted in this narrow follow-on.

## Final source identities

| Path | Status | SHA-256 |
|---|---|---|
| `core/active_position_manager.py` | modified | `0b8da40fdc167cef9a88c39bcc1fa98388ce906bbc45da2d81aa9e6f57efb0e4` |
| `tests/unit/test_apm_runner_trailing_regression.py` | existing untracked focused test file, extended | `03b40c437b48f2e423bcca666f494272af32111417922ee80cbe87c089cba606` |

No commit was created. Cross-process WAL writers remain unsupported. The repository still lacks an operator-controlled recovery/re-arm path for `RECOVERY_BLOCKED`; no fill source was found, so partial fill validation remains `NOT_APPLICABLE`.

## Hermes clarification — terminal snapshot must be revalidated on restart

The post-replace directory-fsync test now exercises a fresh manager from the observed on-disk image. A `LIQUIDATED` or `COOL_OFF` image with `payload=None` is not trusted on bytes alone: recovery requires a dictionary `last_completed_trade`, a nonempty position ID, and exactly one identical history row for that ID. Recovery then fsyncs the WAL file and parent directory before accepting the terminal image. If history is missing, mismatched, duplicated, or either recovery fsync fails, startup enters `RECOVERY_BLOCKED`; fsync failure is exposed as `recovery_status="DURABILITY_UNKNOWN"` and entry admission rejects. Only after proof validation and successful re-fsync is a saved cool-off state resumed.

The original manager that sees a forced persist error likewise retains its in-memory payload, sets `RECOVERY_BLOCKED` plus `DURABILITY_UNKNOWN`, raises, and rejects entry.

Focused APM runner test command after this clarification:

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-wal-home XDG_CONFIG_HOME=/tmp/pr987-r2-wal-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-hermes-terminal -q tests/unit/test_apm_runner_trailing_regression.py
```

Observed: `17 passed in 7.04s`, no skips. The same two pandas dependency-version warnings noted above were emitted. The tests cover missing/mismatched/duplicate history, recovery fsync failure, valid terminal restart with exactly one history row after repeated loads, cooldown only after successful recovery validation, pre-replace failure, and post-replace directory-fsync ambiguity.

Final hashes after the Hermes clarification (these supersede the earlier hashes in this addendum):

| Path | SHA-256 |
|---|---|
| `core/active_position_manager.py` | `aa0f777a01c7f6c1d6a68b3c3ad2b60c687b7b18dd151c1e2a9378f3e838d9d5` |
| `tests/unit/test_apm_runner_trailing_regression.py` | `1e9a5de8e1c1437c0318a933b9b30b69716ade447208a5d69c02141b85f65bd1` |

The final scoped status contains only these two source/test paths and this addendum. `git diff --check` passed. No other source path was changed, and no broader regression run was attempted.

## Superseding clarification — same-setup re-entry leg identity

The prior paragraph above that describes matching terminal history “by that ID” is superseded here: terminal history identity is the composite `(position_id, reentry_count)`, with missing legacy `reentry_count` interpreted as initial leg `0`. This permits a setup to have multiple completed advisory legs while preserving each historical row unchanged. Recovery accepts `last_completed_trade` only when exactly one history row matches that composite key and full content. It does not require contiguous leg indexes. An identical retry for an existing key is idempotent; duplicate rows or differing content under the same key block recovery/liquidation and keep entry admission closed.

The focused tests exercise the GEAR_2_TREND path using position `P`: observed giveback records leg 0 and enters `PULLBACK_WAIT`; restart restores that setup; one confirmed structural re-entry increments to leg 1; leg 1 liquidation preserves leg 0 and stores leg 1 as the terminal summary; two fresh-manager recoveries retain exactly `(P,0)` and `(P,1)`. Controls cover conflicting same-key content, identical retry without duplicate history, and pullback abort with only leg 0. These are advisory state/WAL assertions only; they do not claim fills, broker actions, or realized PnL.

Pre-fix focused command:

```bash
python -m pytest -q --basetemp=/tmp/pr987-r2-leg-red2 tests/unit/test_apm_runner_trailing_regression.py -k 'gear2_pullback_reentry_preserves or liquidation_blocks_conflicting or pullback_abort_with_only'
```

Observed before runtime patch: `3 failed, 17 deselected, 2 warnings in 3.88s`. The two contract failures were: valid two-leg terminal recovery was blocked because matching used only `position_id`, and a conflicting row for the same leg key was appended rather than rejected. The abort case also failed in this initial red run because its test input moved against the CE pullback reference; the fixture was corrected to cross the existing abort boundary and then passed after the patch. That initial abort result is not counted as a code defect.

Final focused command (clean environment, isolated basetemp, no cache provider):

```bash
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/tmp/pr987-r2-leg-home XDG_CONFIG_HOME=/tmp/pr987-r2-leg-home/config PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Volumes/TradeBotFast/worktrees/pr987-egm-remediation /opt/anaconda3/bin/pytest -p no:cacheprovider --basetemp=/tmp/pr987-r2-leg-green-final2 -q tests/unit/test_apm_runner_trailing_regression.py
```

Observed: `21 passed in 3.30s`, exit code 0, no skips. Two existing pandas dependency warnings were emitted (`numexpr` and `bottleneck` versions below pandas recommendations). No full repository or seven-suite run was attempted for this follow-on.

This follow-on changes only `core/active_position_manager.py`, the existing focused APM runner test file, and this addendum. No strategy equations, levels, broker/order/live paths, credentials, or deployment files were touched. Cross-process WAL writers remain unsupported; operator re-arm remains unavailable; no fill source was found, so fill accounting remains unknown/not applicable.

Final hashes after same-setup leg identity changes (supersede all earlier hashes above):

| Path | SHA-256 |
|---|---|
| `core/active_position_manager.py` | `93bc703c83b2662a944e9dac751a1223f73cbdb954d28ba736ecdefe7cc13c5a` |
| `tests/unit/test_apm_runner_trailing_regression.py` | `ed1c4b800a4f3cdbecbcbb815f46a6335d39672b2f9d80777154a94279d4f918` |

The addendum's own SHA-256 is recorded in the completion handoff to avoid a self-referential hash entry.
