# Agent Review: Live Feed Recovery and Replay RCA — 2026-10-12

## Agent Work Contract

- `source_agent`: `grill_me -> hermes -> gsd`
- `action`: `AUDIT_RISK`, `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `GENERATE_PATCH`, `GENERATE_TESTS`
- `title`: Fail-closed feed recovery and evidence-bound offline replay
- `scope`: Repair feed restart verification and callback/socket transition races; require explicit local replay sources and complete outcome horizons; preserve honest retained-evidence and T-1 readiness claims.
- `requested_paths`: Production paths and focused tests listed in the branch diff; RCA work item and this review.
- `allowed_paths`: Scoped production paths, focused tests, and delivery evidence.
- `forbidden_paths`: Broker/order actions, credential changes, risk/freshness gate weakening, live-mode changes, strategy threshold changes, active process restarts, and unrelated UI work.
- `expected_tests`: Feed callback/restart/subprocess, replay source/outcome, evidence, MEG, and related regression suites; exact-head hosted CI.
- `acceptance_proof`: Tests prove restart suppression until fresh verification, retired callback rejection across transitions, IPC restart signaling, offline source binding, rejection of incomplete/ambiguous replay, and preserved unknown/blocked evidence states.

## Scope Guard

The candidate branch is `ram/live-feed-replay-adapter-2026-10-12` at source HEAD `efdd592fea3db13023382e2e1433af4532350d9f`. It contains a stacked 21-commit repair history from merge base `040e834611b9a207ca93380843a9b73ef05d3ac0`. The current `origin/main` is `1fec69212cea655325404d5d16e780082577066e`; the branch is 37 commits behind and 21 ahead. Its current three-dot diff is 61 files, +7,223/-568. This is the full live-RCA/replay fixset, not only the latest callback change.

The branch preserves fail-closed runtime and data authority. It does not certify the live run, authorize execution, or establish that operator-supplied files are authentic or complete.

## Grill Me Review

Adversarial review found no basis to treat file presence, a reconnect request, a partial replay horizon, or a retained ring count as proof of readiness or completeness. The documented RTF incident counts remain qualified by their evidence strength. The current replay capture lacks verified option OHLC and token-to-contract binding; T-1 futures/history and verified heritage ancestry remain prerequisites.

The current GitHub policy presents a hard CI blocker. `.github/workflows/repo-forensics-pr-gate.yml` compares the PR base against pinned baseline `9f1e74c3524b331ebab7f8340ddc056146ac036a`, then rejects changes to its frozen production path set. Current `main` already differs from that baseline in 16 protected paths, and this candidate also changes protected paths including `config/config.py`, `core/feed/**`, `core/kite_depth_ws.py`, and `core/kite_ws_subprocess.py`. The gate has no candidate-specific exception. No documented governed recertification runbook was found. This review does not waive or bypass that gate.

## Hermes Review

Architecture contracts are:

1. Restart eligibility requires fresh same-socket connect, subscribe, and option-tick proof; pending or failed verification blocks restart side effects.
2. Callback batches are immutable and processed in FIFO order; socket-generation transition waits for accepted callback work, and retired generations cannot publish.
3. Callback failure or saturation remains fail-closed and signals supervised child replacement; partial callback side effects are not rolled back.
4. Replay uses explicit offline sources, exact identity/provenance checks, and complete causal horizons. Missing or ambiguous inputs do not create `no_hit` output.
5. T-1 readiness requires the existing pinned, verified heritage contract. Repository-local data inventory does not establish provider authenticity or completeness.

The fresh-process IPC and production callback-latency characteristics remain incompletely characterized; see limitations below.

## GSD Review

The implemented branch adds callback coordination and transition barriers, a fail-closed restart signal, an explicit local replay manifest adapter, replay completeness checks, and corresponding regression coverage. It does not add live broker behavior, change strategy thresholds, weaken risk/freshness gates, or start/stop a live process.

No new configuration keys are introduced by the replay adapter. Callback/restart configuration keys in the branch are:
- `DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING=64`
- `DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC=10`
- `FEED_RESTART_LIFECYCLE_WAIT_SEC=10` (maximum 30 seconds)

Focused validation recorded for the candidate:
- 336 tests passed across callback/restart/subprocess, replay, evidence, MEG, and adjacent regression suites.
- `py_compile` passed for `core/kite_depth_ws.py`, `core/feed/tick_callback_coordinator.py`, and `core/kite_ws_subprocess.py`.
- `git show --check` passed for the implementation commits.
- The latest reviewer found no blocking issue in supervisor-event ordering; those tests use fakes and do not prove signaling across a real spawned child.

These are local results, not exact-head hosted CI.

## QA / Safety Review

High-risk feed paths were reviewed. The implementation retains fail-closed restart and freshness behavior and does not add broker/order calls or alter strategy/risk thresholds. No live process was restarted or modified during this work.

Independent QA remains partial:
- IPC wiring tests use test doubles rather than a real spawned child.
- No production callback/cutover latency or callback-side-effect rollback proof exists.
- Supplied capture files do not meet the replay adapter's verified option OHLC contract.
- Exact-head CI is not green. The frozen PR818 gate is expected to fail under current baseline and protected-path policy; this is a repository governance blocker, not a passing check.

## Acceptance Proof

Locally recorded acceptance evidence:
- Restart and callback tests: pending/failed proof blocks restart; transition and retired-generation tests cover callback ordering and socket cutover.
- Replay tests: absent/mismatched/incomplete sources and ambiguous horizons fail closed.
- Adjacent evidence tests preserve unknown counts and blocked T-1 readiness.
- Combined focused suite: 336 passed, as recorded in the work item.

Hosted acceptance is **not met**. It requires all applicable checks green on the exact PR head and an authorized resolution of the frozen-flow baseline/recertification policy. A failed or skipped policy check is not acceptance.

## Runtime Proof Required After Merge

After an authorized deployment, a read-only observation must bind the exact producer SHA and run/session identity, verify fresh same-socket recovery proof, measure callback queue/cutover behavior, and confirm child replacement signaling under a real spawned-process failure. Do not restart or initiate that observation without the required human operational authorization.

## What This PR Does Not Prove

- Live readiness, production verification, or permission to restart the live run.
- Strategy profitability or executable trading authority.
- Authenticity/completeness of the operator-supplied Upstox files.
- Exact option outcome replay from the captured LTP/bid/ask/depth snapshots.
- T-1 futures history or a verified heritage graph.
- Real-process IPC reliability or production callback latency.
- Green CI or merge readiness.

## Human Approval

The user authorized preparing and raising a PR and working toward green CI. That authorization does not waive the frozen-flow policy, authorize changing its baseline/gate, authorize merge, or authorize live/broker/order actions.

## Rebase and CI Follow-up

The branch was rebased onto `origin/main` at `1fec69212cea655325404d5d16e780082577066e`. The old PR head `877472b2d395e1298c564223a503a1be4c9a87c7` produced two hosted unit-test shards with 8 and 9 failures. The CI RCA tied these to an immutable-source hash mismatch, test leakage from governed observation-plan/callback state, an import-missing snapshot persisting a stale intended-token count, and a test assuming synchronous callback artifact persistence.

The repair preserves production precedence and asynchronous callback persistence. The import-missing snapshot now reports the request-local token count. Tests reset only the state they own and wait with a bounded timeout for queued persistence. Four callback/restart environment settings are validated in `core/feed/callback_config.py`, outside hash-pinned `config/config.py`; defaults are queue max 64, transition wait 10 seconds, lifecycle wait 10 seconds, and blocked-log cooldown 30 seconds. Invalid values fall back to those defaults and valid values are clamped to documented bounds. No risk, freshness, kill-switch, or live-mode gate was weakened.

Validation after the rebase: the previously failing test modules plus the new config tests passed locally (**74 passed**). On the pushed intermediate head `a6719bdc38d96d78686e3f128f2f762cbfb82455`, `agent-review-evidence`, exact-SHA identity, candidate safety tests, documentation/contract gate, base-authority checks, and secret scan passed. `pr818-live-flow-freeze-target` failed as expected under the frozen protected-path policy; the main unit-test, feed-smoke, focused-contract, verification, and trusted-base evidence jobs had not completed at the time of this note. This is not a green exact-head CI result or live-readiness approval.

The PR remains draft. Do not bypass the frozen-flow gate or promote these local tests to hosted CI evidence. Recheck every status against the latest PR head after this follow-up is pushed.
