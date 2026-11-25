# PR #987 R4 WAL Ownership Verification

## Verdict: HOLD

The R4 code closes the reproduced sidecar-path collision in the tested configuration and passes the scoped ownership and R3 regression batches. Rollout is blocked: startup intentionally refuses an existing regular legacy `<wal>.lock`, and the checked-out runtime contains such files. There is no operator migration proof, and the deployment filesystem and its `flock` semantics are unknown (`DEPLOYMENT_UNVERIFIED`). Senior QA returned **BLOCK**. These results support engineering review of the patch only; they do not establish merge readiness, production readiness, broker fill authority, or permission to trade.

No strategy thresholds, broker/order paths, credentials, LIVE settings, or running processes were changed. No broker API call, order action, commit, push, merge, or deployment occurred. CI was not run.

## Identity and scope

- Worktree: `/Volumes/TradeBotFast/worktrees/pr987-egm-remediation`
- HEAD/baseline: `94ab77b554d7540adee68746d8b5016e92ff7d34`
- Branch: `ram/pr987-egm-remediation`
- Work item: `BUG-PR987-R4-WAL-SIDECAR-COLLISION-001`, under the locally created Epic `EPIC-APM-WAL-DURABILITY-001` and Feature `FEAT-APM-WAL-OWNERSHIP-001`. The user authorized creating this narrow local hierarchy when canonical IDs were unavailable. It is not proof of universal task-platform intake integration.
- Scope is the APM WAL ownership identity collision, its offline tests, and this verification report. Other R3/PR changes and runtime artifacts in the worktree predate or sit outside the R4 ownership change; they were not silently treated as R4-owned.

## Source identity and inventory

Current SHA-256 values, rechecked after QA:

| R4 file | Status | SHA-256 |
|---|---|---|
| `core/active_position_manager.py` | modified | `c06bc560635bee4a5fa75d99eac5321e1eeceb3ae5c4a3e1259e1676eb22b21b` |
| `tests/unit/test_apm_wal_process_ownership.py` | untracked/new | `38fd96ed2501f3965caf919c3701009701c225645fa657bae3780e510eb29e83` |

R4 also created or updated the specifically authorized delivery evidence files: the Epic, Feature, Bug record, work-item evidence JSON, and evidence registries. The final report is this new file. The worktree contains other pre-existing uncommitted PR/R2/R3 files and generated `runtime/` artifacts; this is not a clean-worktree assertion. `git diff --check` passed. No unrelated runtime artifact was intentionally edited as part of R4. The existing runtime regular `.lock` files were preserved and are the rollout blocker described below.

## Phase 1 — Collision reproduction

### Before R4

The pre-R4 two-process reproduction used the previous R3 implementation (`core/active_position_manager.py` SHA-256 `77faf41dc548ac7f90963390ad6c9eebef2e61ecbb80dc2365fba5ed3bb02771`). Process A (PID 54051) owned `trade.json` through sidecar inode `(dev=16777233, ino=391637565)`. Process B (PID 54090) opened that sidecar pathname as its own WAL, acquired a different sidecar inode `(16777233,391637348)`, wrote 266 bytes, and atomically replaced A's sidecar path with inode `(16777233,391637568)`. While A still held the original inode open, process C acquired the replacement inode. Thus A and C both believed they owned the same effective WAL namespace. CodeRabbit's Major collision finding was reproducible.

Prior R3 alias checks showed relative paths, `./`/`..` spelling, parent-symlink aliases, and leaf-symlink aliases converged under `Path.resolve`. Hard-link aliases did not: independent managers could acquire distinct sidecars while the WAL paths referenced one inode.

### After R4

The WAL lock identity is derived from the canonical parent directory's device/inode and a Unicode NFC + casefold normalized leaf. The resulting SHA-256 name is kept in a persistent `.apm_wal_locks/` directory, outside the atomically replaced WAL pathname. WALs in that reserved namespace are rejected. Existing WAL files with `st_nlink > 1` are rejected before recovery and rechecked before atomic persistence. The process test `test_independent_process_cannot_treat_owner_lock_as_wal_or_steal_owner` starts an owner and independent contenders: use of the legacy sidecar spelling is rejected before WAL creation/replacement, the original owner-lock dev/inode stays unchanged, and a third contender for the real WAL is blocked while the first owner is alive.

The before/after evidence is from process-level tests and captured inode identities, not only a direct helper invocation. After R4, the test suite passes the alias and hard-link cases, stable lock identity across WAL replacement, release and successor acquisition, abnormal process exit/recovery, concurrent startup, lock path tampering, unsupported lock primitives, and bounded identity-checked ENOENT retry. The actual deployment mount remains unknown, so these results are bounded to the tested mounted APFS volume and local isolated test filesystem.

## Minimal corrective design and limits

The implementation keeps a single-writer model. It does not add a multiwriter transaction protocol. It rejects WAL hard links, canonicalizes supported path aliases, opens the owner lock through a directory descriptor with `O_NOFOLLOW`, validates lock-file and directory inode identity, uses nonblocking exclusive `flock`, and checks lock identity before persistence. The lock file is stable and is not replaced with the WAL. A single retry for `ENOENT` is allowed only after parent and lock-directory identities revalidate; persistent or changed-namespace failures stop startup with an explicit `WALOwnershipError`, without a lexical-path fallback.

When the legacy sibling sidecar is absent, the manager creates a symlink to its reserved stable lock. This makes older R3 code using `O_NOFOLLOW` fail closed rather than transparently coexist. If a regular file, directory, broken/wrong symlink, or other non-alias already occupies that path, the new manager fails closed and leaves it untouched.

**Migration blocker:** the checked-out runtime has existing regular files at `runtime/sentinel_apm_wal.json.lock` and the NIFTY/SENSEX/BANKNIFTY sibling WAL lock names. A new manager refuses startup when its legacy sidecar pathname is occupied by a regular file. Those artifacts were not deleted, converted, or modified. There is no verified stop-owner, backup, migration, restart, and recovery procedure for a live deployment. Do not remove those files while an owner may be running. The patch therefore cannot be promoted as an in-place upgrade without a separately approved and validated migration plan.

**Filesystem blocker:** `/Volumes/TradeBotFast` was remounted as an APFS external disk image (UUID `61C7D549-7E73-4A64-AE66-8E19C8D6C85F`; 19.7 GB free at check). APFS test success is not proof of the actual deployment filesystem. Lock correctness on the deployed mount is `DEPLOYMENT_UNVERIFIED`.

## Tests and evidence

QA used Python 3.12.2 with sanitized environment, disabled pytest plugin autoload, bytecode writing disabled, and temporary test working/basetemp locations under `/private/tmp` to avoid the pre-existing runtime `.lock` files in the repo checkout. Commands were run against this exact source hash; QA confirmed hashes stayed unchanged throughout its run.

| Validation | Result | Interpretation |
|---|---:|---|
| `tests/unit/test_apm_wal_process_ownership.py` | exit 0; 25 passed, 0 skipped | Ownership, aliases, cross-process collision, failure and recovery cases passed. |
| Scoped R3 regression batch (21 focused APM + 19 supplemental + 250 historical selectors + smoke teardown selectors and named Sentinel regression selectors) | exit 0; 318 passed, 0 skipped | Exact scoped batch passed; not a repository-wide pass. |
| Fresh N-way ownership launch stress | 9 groups × 4 processes; each group had exactly 1 owner and 3 owner-busy outcomes | Repeated concurrent startup evidence on test host only. |
| Full `test_sentinel_advisor_hardening_003.py` | remediation: 18 failed / 51 passed; baseline: 19 failed / 50 passed | All 18 remediation failures matched baseline; one baseline-only failure now passes. No new failure identified in this suite; suite remains failing. |
| Smoke harness focused teardown selectors | 3 passed | Confirms cleanup and lock release only; does not prove a trade. |
| `git diff --check` | passed | Whitespace/conflict-marker check only. |

QA's batch included isolated execution for the ownership and regressions. The checked-out runtime's pre-existing regular `.lock` files caused an unrelated advisor test to fail at manager initialization when run from the repository CWD; that selector passed from a fresh temporary CWD, and the existing files' bytes/mode/inode/mtime were preserved. This is an environment/path occupancy condition with real upgrade relevance, not a test workaround that changes production validation.

The 18 matching hardening003 baseline failures include epoch/timestamp boundary assertions, key/underlying mismatch cases, stale-gate behavior, OR validation, rollover, post-lock dispatch, and companion OR checks. Their exact node IDs are retained in `PR987_R3_TARGETED_REMEDIATION.md`; this report does not recast them as passing. CI was intentionally not run per the user's standing direction to leave CI.

Exact independent QA commands (macOS, Python 3.12.2, sanitized environment; CWD `/private/tmp/pr987-r4-luna-cwd`):

**Ownership suite — exit 0, 25 passed, 0 skipped**

```sh
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/private/tmp/pr987-r4-luna-home TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -S -c 'import os,sys; repo="/Volumes/TradeBotFast/worktrees/pr987-egm-remediation"; sys.path.insert(0,repo); sys.path.append("/opt/anaconda3/lib/python3.12/site-packages"); os.chdir("/private/tmp/pr987-r4-luna-cwd"); import pytest; raise SystemExit(pytest.main(["-p","no:cacheprovider","--basetemp=/private/tmp/pr987-r4-owner-final","-q",repo+"/tests/unit/test_apm_wal_process_ownership.py"]))'
```

**Scoped R3 regression batch — exit 0, 318 passed, 0 skipped**

```sh
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin HOME=/private/tmp/pr987-r4-regression-home TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -S -c 'import os,sys; repo="/Volumes/TradeBotFast/worktrees/pr987-egm-remediation"; sys.path.insert(0,repo); sys.path.append("/opt/anaconda3/lib/python3.12/site-packages"); os.chdir("/private/tmp/pr987-r4-luna-cwd"); import pytest; tests=[repo+"/tests/unit/test_apm_runner_trailing_regression.py",repo+"/tests/unit/test_pr987_r2_controlled_remediation.py",repo+"/tests/unit/test_apm_wal_process_ownership.py",repo+"/tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_repeated_calls_release_wal_ownership_and_keep_sidecars",repo+"/tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_reports_shutdown_failure_without_masking_existing_error",repo+"/tests/unit/test_sentinel_premarket_and_sizing_hardening.py::test_smoketest_exception_path_releases_wal_ownership",repo+"/tests/unit/test_sentinel_realtime_journal.py",repo+"/tests/unit/test_sentinel_regime_router.py",repo+"/tests/unit/test_sentinel_rbfn_scenarios_s2_s4_s7.py",repo+"/tests/unit/test_sentinel_optionmate_execution_hardening.py",repo+"/tests/unit/test_sentinel_advisor_hardening_005.py",repo+"/tests/unit/test_sentinel_optionmate_rbfn_auction.py",repo+"/tests/unit/test_sentinel_advisor_hardening_003.py::test_mode5_bar_abstains_before_history_mutation_without_valid_or"]; raise SystemExit(pytest.main(["-p","no:cacheprovider","--basetemp=/private/tmp/pr987-r4-regression-final","-q",*tests]))'
```

QA also reported nine N-way process-start groups with four processes each; every group produced one owner and three owner-busy results. The exact stress harness command was not retained, so this remains QA-reported rather than directly reproducible evidence here. Full `test_sentinel_advisor_hardening_003.py`: remediation exit 1 (18 failed, 51 passed); baseline exit 1 (19 failed, 50 passed). No test result is claimed to be a full-suite pass.

## Synthetic OR smoke finding

The unchanged smoke harness's expected `IN_FLIGHT` assertion is not evidence that the WAL fix lost a valid production entry. The harness injects synthetic cached RBFN signal and synthetic depth; its OR provenance is `SYNTHETIC_REPLAY_SEED`. Live-mode validation requires exact trusted `UPSTOX_V2_1M_EXACT_30` provenance and trusted proofs. Therefore the engine correctly stays in `STANDBY` for that synthetic fixture. The test failure must not be “fixed” by weakening OR trust. The three smoke selectors in the scoped batch validate shutdown/teardown only; no successful trade is claimed.

## Independent role outcomes

- Business Analyst: PASS for narrow R4 requirement definition and acceptance criteria.
- Product Owner (scope): accepted narrow technical scope before development. Final product acceptance is not established by that scope acceptance.
- Grill Me: confirmed the original collision and hard-link gap; identified regular legacy sidecars as migration-blocking, and noted the ENOENT path's fail-closed behavior and residual startup availability limitation.
- Hermes: defined stable reserved lock identity, hard-link rejection, compatibility sidecar behavior, retry invariant, and fail-closed contracts.
- GSD: implemented only the R4 APM ownership and test scope; exact current hashes above.
- QA: 25 ownership tests and 318 scoped R3 selectors passed; full hardening003 remains failing with baseline comparison as above.
- Technical & Quant Analyst `/root/r4_tq`: four source-bound challenges; quant portion NOT_APPLICABLE. Hermes answered each. Dispositions: Q1 legacy migration — UNRESOLVED; Q2 parent-directory TOCTOU — UNRESOLVED; Q3 deployed filesystem/flock semantics — UNRESOLVED; Q4 NFC/casefold alias behavior — UNRESOLVED pending explicit tests/documentation. Hermes additionally found full old-R3 manager integration and the race between old R3 sidecar creation and new R4 alias creation are not proven; the `O_NOFOLLOW` primitive test alone is not a mixed-version integration test. Natural ENOENT events remain unexplained; deterministic injected retry behavior is covered, but their cause is UNKNOWN.
- Senior QA `/root/r4_seniorqa`: **BLOCK**. In addition to legacy migration and deployment FS, it identifies the unclosed parent-directory TOCTOU, missing case/Unicode tests, and incomplete old-R3 mixed-version integration/race proof.
- UAT `/root/r4_uat`: **PASS** on final report retest. This accepts report clarity and traceability only; it does not change the HOLD or Senior QA BLOCK. Final PO `/root/r4_po_final`: **ACCEPTED** for the scoped report/work-item deliverable after retest. This acceptance does not clear technical blockers or authorize merge, release, deployment, or trading.
- Universal task-platform intake integration: UNSATISFIED. This local work item hierarchy was authorized and recorded, but no evidence shows every task platform request is automatically linked.

### Technical challenge → Hermes response → disposition

| ID | T&Q challenge and evidence | Hermes response and evidence | Disposition |
|---|---|---|---|
| TQ-R4-1 | How can an operator safely migrate existing regular `<wal>.lock` files while distinguishing an active R3 owner from stale data or a legitimate WAL? The checked-out runtime has regular sidecars; tests only prove nonmutation and fail-closed startup (`core/active_position_manager.py:385-406`; `tests/unit/test_apm_wal_process_ownership.py:488-508`). | UNRESOLVED. No process census/stop evidence, backup/quarantine procedure, or operator migration is present. Preserve files and require a separately authorized maintenance plan. | UNRESOLVED; rollout blocker. |
| TQ-R4-2 | Does the parent directory remain stable between lock validation and WAL replacement? Validation is path-based (`core/active_position_manager.py:292-310`); temp creation and `os.replace` use lexical paths (`:526-536`). No parent-swap race test exists. | UNRESOLVED. Parent device/inode is rechecked before persistence, but no held parent dirfd makes the check+replace atomic and parent immutability is not enforced. | UNRESOLVED; concurrency blocker. |
| TQ-R4-3 | Are `flock` semantics proven on the deployed WAL mount? | UNKNOWN. Code checks `flock`, `O_NOFOLLOW`, and `dir_fd` availability (`:312-318`); that does not prove deployed mount semantics. | UNRESOLVED; `DEPLOYMENT_UNVERIFIED`. |
| TQ-R4-4 | Are NFC/NFD and case-only aliases characterized? | Partially answered by identity normalization NFC + `casefold` (`:201-205`). On case-sensitive filesystems, distinct names may share a lock, causing conservative contention. No targeted case/Unicode tests were found. | UNRESOLVED pending explicit characterization tests/docs. |

Hermes separately noted that the old-R3 compatibility claim is incomplete: `test_legacy_alias_symlink_is_valid_but_old_nofollow_open_fails` proves OS `O_NOFOLLOW` returns `ELOOP` (`tests/unit/test_apm_wal_process_ownership.py:542-552`), but does not instantiate the pinned R3 implementation or exercise both orderings of the old-R3 sidecar-open/new-R4 alias-creation race. The observed natural ENOENT events also have no captured path/errno/dirfd reproduction; deterministic injected ENOENT branches pass, but the original incident cause remains UNKNOWN. These are open proof gaps, not resolved findings.

## Remaining blockers and allowed next step

1. Define and separately validate an operator-controlled migration for existing regular sibling sidecars, preserving evidence and ensuring no old owner remains. Never unlink/replace a lock file while a manager may still own it.
2. Identify the real deployment process, WAL paths, mount/filesystem, and supported locking semantics; validate cross-process exclusion and recovery there before any rollout claim.
3. Full hardening003 remediation and baseline command lines and failure node IDs are recorded in `PR987_R3_TARGETED_REMEDIATION.md`; retain the failing 18/51 and 19/50 outcomes as blockers, not as a pass.
4. No report acceptance gate remains open. Technical readiness remains blocked by items 1–3 and the Senior QA findings; do not infer release approval from PO acceptance.
5. Do not merge, deploy, or enable trading based on this report. The next allowed work is read-only evidence completion and a separately scoped migration/filesystem verification plan.

## Rollout notes

- New configuration keys: none.
- Strategy, levels, thresholds, broker behavior, orders, risk gates, kill switches, feed freshness, and SIM/PAPER/LIVE semantics: unchanged.
- Tests added in R4: expanded process ownership and adversarial lock identity tests in `tests/unit/test_apm_wal_process_ownership.py`.
- Rollout: none performed. Remain HOLD until the migration and deployed-filesystem blockers are addressed and required review gates return positive evidence.
- Rollback: keep the patch unmerged/unreleased; preserve WAL and sidecar artifacts. Do not unlink lock files as cleanup.
