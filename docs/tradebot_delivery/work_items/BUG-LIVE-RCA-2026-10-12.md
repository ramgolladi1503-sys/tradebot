# BUG-LIVE-RCA-2026-10-12 — Live feed recovery and replay readiness

## Identity

- Work Item ID: BUG-LIVE-RCA-2026-10-12
- Type: BUG
- Parent Epic: LIVE-RELIABILITY-RCA-2026-10-12
- Parent Feature: Feed recovery verification and evidence-backed replay
- Title: Stop unverified feed restart loops and prevent unsupported replay claims
- Current State: IN_DEVELOPMENT
- Priority: P1 — trading safety and evidence integrity

## Business Goal

Repair confirmed reliability and evidence defects before another live observation. Keep the observer read-only and fail closed. Establish whether operator-supplied historical Upstox data can satisfy a particular replay or T-1 prerequisite without treating file presence as data authority.

## Current Behavior

- A feed restart could be attempted while its preceding restart verification was still pending or had failed. The watchdog’s recovery latch could continue requesting recovery without fresh connect, subscribe, and option-tick proof.
- The older active runtime logged `FEED_RESTART_FORCE_FULL_PATH` before acquiring the restart lock and before the in-lock breaker/concurrency checks. This event meant “full restart path requested,” not “restart attempt began,” so counting it as a restart inflated incident totals. Current retained run log counts are 6,451 request records, 5,694 breaker-block records, and 757 concurrency-block records; the latter two sum to the request count. The repair worktree renames this event to `FEED_RESTART_FULL_PATH_REQUESTED`, sets `restart_attempted=false`, and leaves `FEED_FULL_RESTART_BEGIN` as the attempt-start event.
- **Historical runtime snapshot:** the active observer PID 6069 / child PID 6107 was reported from `/Volumes/TradeBot/worktrees/mros-dynamic-releasestore-binding-v1` at base SHA `9cf2e5381f2f8d3d33d75eb8bc8324b92e401774`; its 15:02 IST artifact said `RESTART_VERIFY_FAILED`, `feed_ok=false`, websocket disconnected, `restart_attempt_allowed=true`, `restart_attempted=false`, and no live option feed for the three tracked indices. This was evidence about that runtime snapshot, not current process state. The original repair worktree path/branch was historical. Current follow-up changes are in `/Users/madhuram/.codex/worktrees/live-feed-replay-followup/tradebot`, branch `ram/live-feed-replay-adapter-2026-10-12`, based on `378e1631917744adae8df3f9a3e0f6340004380d`, and remain uncommitted. They are not deployed or live-validated.
- A retired `on_ticks` callback could pass the wrapper generation check, pause across socket cutover, then update shared freshness/runtime state. A verifier-only generation-bound tick map did not prevent those shared mutations.
- Follow-up review found that runtime snapshot queue rejection could invoke a synchronous direct-artifact fallback while the callback held `_SOCKET_GENERATION_LOCK`. The fallback is now disabled for `source="on_ticks"`; the runtime store still marks persistence durability degraded, while non-callback callers retain legacy fallback. The queue-full rotating-file error log and the callback caller's `FEED_RUNTIME_STORE_WRITE_ERROR` log are also suppressed for this producer because both execute synchronously; runtime rejection counters and the shared durability latch remain the failure evidence. Focused tests exercise real runtime-store queue rejection and the registered `on_ticks` callback, verify rejection/degradation, and assert no callback artifact fallback/error log. Non-callback fallback remains covered. The broader adjacent-contract suite passes (238 passed, zero deselections). This closes only the rejection-specific synchronous fallback/log path. The generation lock still spans the larger callback body and runtime enqueue, and representative lock-hold/cutover latency is unmeasured.
- An in-flight verifier could compute proof outside the lock and later commit it against a newer pending verification. A monotonic generation check now binds stage/success/failure commits to the attempt and socket generation that supplied the proof inputs. Verification is armed before connect callbacks, retired-socket stages are rejected, and snapshot formatting cannot run a second recovery proof.
- Analytics replay previously had an implicit `core.market_data` route, which can reach Kite historical APIs. The route is removed in the current worktree. Batch replay now refuses to write outcomes for nonempty input unless a caller provides a series loader.
- **At initial review:** that callback seam was not a certified Upstox-file loader, the CLI could not supply it, and it carried no source receipt. **Current follow-up:** an explicit local-only CLI manifest adapter exists and requires exact event contract, operator-supplied file/master hashes, session, interval, timestamp semantics, and complete OHLC coverage. The adapter does not authenticate provider claims or prove source completeness; no source meeting its contract has been verified. Existing captured bid/ask/LTP/depth ticks must not be converted to OHLC and do not prove exact event-to-option-contract coverage. This adapter enables a constrained offline workflow but does not resolve the missing-data RCA.
- Replay can currently label a partial lookahead with no threshold hit as `no_hit`. That is unsupported evidence and must be withheld until a complete, causally valid horizon is established.
- Independent full-fixset QA found two additional fail-open evidence defects: a missing event timestamp could produce `no_hit` using wall-clock time, and JSON booleans passed integer schema/count checks because Python equates `True` with `1`. Both now fail closed: replay raises `IncompleteOutcomeWindowError` for missing timestamp or outcome levels, and retained evidence requires exact integer types.
- MEG summaries validate retained JSONL row shape, semantic hashes, evidence kind, run/session identity, and safety fields while holding the same-process writer lock. Reported row counts are retained-ring lower bounds. Cumulative counts remain unknown in all cases because the bounded ring has no durable generation/sequence continuity proof. The observer preserves unknown as `null` through compatibility fields instead of coercing it to zero.
- The MEG launch plan reports pre-session observer/subscription readiness separately from strategy T-1 readiness. Its T-1 reference status remains `BLOCKED_HERITAGE_MANIFEST_UNCONFIGURED` or `HERITAGE_MANIFEST_REFERENCE_CONFIGURED_UNVERIFIED`; neither status certifies T-1 inputs. The runtime heritage loader independently verifies the pinned graph and leaves strategy prerequisites blocked on failure.
- Live T-1 prerequisites load only from an explicitly pinned, verified heritage graph below the approved session root and matching the target session. A legacy inventory or arbitrary previous-day file is intentionally insufficient.

## Expected Behavior

- A new full restart is suppressed while verification is `PENDING` or `FAILED`. The recovery latch remains set until independent fresh feed proof succeeds.
- Every proof result and diagnostic stage update is committed only to the same verification generation that supplied its proof inputs.
- Replay never invokes broker/network history implicitly. Batch output is not created or replaced when a required local source is missing, corrupt, mismatched, or incomplete.
- `no_hit` is emitted only when the full requested observation horizon is established. Partial or ambiguous data is blocked, not counted as a resolved no-hit.
- Export and traversal counts state their scope and never imply completeness that the retained evidence cannot prove.
- T-1 values are used only when the supplied artifacts satisfy the existing pinned heritage-graph contract, exact target session/instrument/strategy contract, chronology, and independent verification.

## In Scope

- Restart-verification gate and watchdog behavior already changed in the current isolated worktree.
- Offline replay source boundary and outcome-window completeness defect.
- Retained-rotation accounting claims and tests.
- RCA of the 30 issues asserted in `/Users/madhuram/Desktop/1.rtf`, with each claim marked by evidence strength.
- Determine the precise T-1/heritage inputs required for supplied Upstox data to be considered; do not grant runtime or live authority from file presence.

## Out of Scope

- Any order, broker, credential, risk threshold, feed freshness gate, strategy threshold, or LIVE-mode change.
- Starting, stopping, restarting, or signaling active feed/capture/observer processes.
- Treating underlying index candles or generic raw ticks as option contract outcome data.
- Declaring strategy profitability, live readiness, or production verification.
- Repairing source-data gaps without the actual source artifacts and source contract.

## Dependencies

- Exact local option contract data covering the event and requested lookahead, if option outcome replay is required.
- For T-1 strategy shadow prerequisites: source files with required daily/futures/calendar semantics; an assembled, content-addressed heritage graph; an independent verifier pass; and a manifest path under the configured approved root.
- Runtime evidence bound to a run/session identity for any claim about the live event.

## Requirement Traceability

| Requirement ID | Requirement | Source | Acceptance criterion |
|---|---|---|---|
| LIVE-RCA-01 | No repeated full restart without successful verification | User request and restart diagnostics | Tests prove `PENDING`/`FAILED` block restart side effects, while fresh proof can recover and allow a later attempt |
| LIVE-RCA-02 | Historical replay is offline and evidence-bound | User question about prior-day Upstox files | No implicit network/broker fallback; no output when exact source binding or full coverage is absent |
| LIVE-RCA-03 | Incomplete/ambiguous horizons cannot be reported as `no_hit` | Adversarial review of replay behavior | Incomplete coverage and same-candle target/stop ambiguity abort before output creation/replacement; early single-sided hits require a contiguous prefix |
| LIVE-RCA-04 | Rotation summaries do not claim unavailable history | Rotation audit | Corrupt/holey rings produce only validated retained lower bounds or unknown totals |
| LIVE-RCA-05 | T-1 data cannot be promoted from unverified file presence | Existing heritage graph contract | Exact pinned graph, target identity and independent verification are required; otherwise fields remain blocked |
| LIVE-RCA-06 | Incident RCA separates evidence from claims | Attached RTF and current read-only artifacts | Every issue is labeled confirmed, plausible, or unverified, with evidence source and limitation |
| LIVE-RCA-07 | A stale verifier or retired socket cannot certify recovery | Senior QA concurrency review | Event-controlled tests prove stale proof results and callbacks from replaced sockets cannot mutate or satisfy a pending verifier |

## Safety / Risk Constraints

- Broker/order impact: None; `broker_api_called=false`, `is_order_action=false`.
- LIVE/PAPER/SIM impact: No mode change; `allowed_for_live_execution=false` for produced evidence.
- Risk-gate impact: No weakening or bypass.
- Feed-freshness impact: No weakening or fallback.
- Data/evidence impact: Local read-only inputs only; preserve unknown/blocked states and provenance.
- Required human approval: User approved a fail-closed restart gate. No approval to start another live run or grant live authority is inferred.

## Architecture Impact

- Components touched: `core/kite_depth_ws.py`, `config/config.py`, `core/analytics/outcome_replay.py`, `core/read_only_live_evidence.py`, MEG launch-plan/bridge code, and their targeted tests (current uncommitted worktree).
- Interfaces/contracts affected: Restart verification gate; offline replay loader seam; launch-plan heritage reference; retained rotation summary semantics; watchdog event semantics (`FEED_RESTART_FULL_PATH_REQUESTED` means requested, while `FEED_FULL_RESTART_BEGIN` means attempt started).
- Existing infrastructure reused: Restart-verification state machine, `core.market_heritage_graph.load_verified_t1_prerequisites`, content-addressed heritage verifier, bounded JSONL rotation writer.
- Replay infrastructure: the current follow-up adds a strict local manifest adapter for operator-supplied option OHLC and hashed instrument-master bytes. No qualifying local data source is verified; provider authenticity/completeness remain unverified, so do not treat adapter availability as a replay-data fix or live readiness.
- New config key: `FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC` (default `30.0` seconds) rate-limits repeated blocked-verification diagnostics. It does not change verification requirements or restart eligibility.
- Schema/migration: no persistent data schema migration. Watchdog log consumers that treated `FEED_RESTART_FORCE_FULL_PATH` as a completed/started attempt must migrate to `FEED_RESTART_FULL_PATH_REQUESTED` for intent and `FEED_FULL_RESTART_BEGIN` for attempt start. Replay aborts on unscorable missing timestamp/levels before atomically replacing output; JSONL writes use unique same-directory temporary files, cleanup failed writes, and preserve prior output bytes.
- High-risk paths touched: `core/kite_depth_ws.py` restart gate, narrowly scoped to fail-closed restart suppression; no broker/order/strategy code.

## Acceptance Criteria

- [x] Restart attempts are blocked for `PENDING`/`FAILED` verification and no broker/order action is introduced.
- [x] Verifier success/failure and stage markers are generation-bound under the verification lock.
- [x] Batch replay refuses to write results without an explicitly supplied local series loader.
- [x] Incomplete lookahead, missing expected bars, and same-candle target/stop ambiguity cannot yield `no_hit`.
- [x] Missing event timestamp or outcome levels cannot manufacture a `no_hit` row or synthetic event time.
- [x] Event-anchored interval-start grids accept the 09:15 IST 2-minute exchange-session boundary and reject missing exact source bars.
- [x] Retained evidence totals validate row identity/hash and are labelled lower bounds; cumulative totals remain unknown without durable continuity proof.
- [x] Retained evidence counting rejects corrupt/hash-invalid rows and incomplete rotation rings; unknown cumulative counts remain `null` in runtime summaries.
- [x] Hash-valid retained evidence with boolean `schema_version` or traversal count is rejected for both traversal and export evidence kinds.
- [x] Fresh connect and subscribe evidence from the active socket is required before a FAILED verifier can recover; snapshot formatting cannot run a second recovery proof.
- [x] Tick callback ingestion is serialized with socket cutover; a callback carrying a retired generation is rejected before it can update shared freshness, persistence, or runtime state.
- [x] Full-path request diagnostics are distinct from restart attempts; tests prove breaker-raced requests carry `restart_attempted=false` and do not emit attempt-begin.
- [x] Runtime snapshots force `restart_attempt_allowed=false` while restart verification is pending or failed, even when a caller supplies stale `true`.
- [ ] Operator-supplied option data is bound to exact event contract, file digest, session, interval, timestamp semantics, and complete coverage before it can produce an outcome.
- [x] Independent QA full-fixset pass after the latest defect/fix/retest loop (275 tests, zero deselections, isolated HOME).
- [x] Senior QA re-reviewed the latest stale-callback, startup, and subscription lock-order fixes; callback critical-section latency remains flagged.
- [ ] UAT confirms the contract/report behavior without claiming a trading edge.
- [ ] Product acceptance and release gates remain pending.

## Development Plan

- Allowed paths: currently changed files listed under Architecture Impact; additional paths require a revised scope and review before edits.
- Forbidden paths: credentials/env files, order/broker/risk/strategy code, active runtime artifacts, and live process control.
- Expected implementation: Preserve completed fail-closed repairs; fix only evidence-supported defects with failing behavior tests first; block unsupported data claims.
- Required developer tests: restart negative and recovery behavior; offline fallback tripwire; no output on missing/invalid source; partial and gapped window rejection; rotation corruption/hole cases.

## QA Attack Plan

- Happy path: Fresh restart proof permits a later recovery attempt; complete exact-contract local history supports deterministic replay.
- Negative path: Verification remains pending/failed; source path/hash/identity is absent or mismatched; broker/network fallback is attempted.
- Boundary conditions: Event at bar boundary, same-candle stop/target, window ending at session close, and history ending one bar early.
- Stale/missing/corrupt data: Missing file, truncated Parquet, bad hash, wrong expiry/strike/right, wrong session/timezone, duplicate/out-of-order rows, synthetic/mock/fallback flags.
- State-transition failures: Failed verification must not clear its recovery latch absent new proof.
- Concurrency/order: Verification state changes between scheduler check and restart lock; output file must remain byte-identical when replay batch aborts.
- Regression targets: Current focused restart, analytics, evidence, launch-plan, and MEG tests.

## UAT Criteria

- Report distinguishes ordinary fail-closed gates from proven faults and unverified RTF claims.
- No-hit is not used as a substitute for incomplete source data.
- Previous-day data is described as potentially useful only for the specific prerequisite it proves; file presence alone does not authorize runtime use.

## Release Gates

- [x] Requirements and safety constraints recorded
- [x] Architecture review recorded for restart gate and replay/retention contract
- [x] Developer focused validation: 392 passed across changed components and adjacent contracts with a temporary isolated home. The smaller scoped suite with the real home had 274 passed and one failure because the active observer owns the shared home lock; isolated runs passed the lock test without omitting it.
- [x] QA_PASSED — independent full scoped retest: 275 passed with no deselections under isolated HOME; missing-time/levels and boolean-as-integer defects are covered and closed.
- [x] Callback certification regression pair: 43 passed, zero deselections under isolated HOME. This covers the registered callback/persistence contract and fixture callback SLA; it does not measure representative batch/persistence lock-hold or socket cutover latency.
- [x] Restart diagnostic event contract now distinguishes `FEED_RESTART_FULL_PATH_REQUESTED` from `FEED_FULL_RESTART_BEGIN`; targeted tests verify blocked requests cannot be mistaken for started restarts.
- [x] SENIOR_QA targeted re-review passed stale-callback, startup, and subscription lock ordering. Lock-hold latency remains flagged and unmeasured.
- [ ] UAT passed
- [ ] PRODUCT_ACCEPTED
- [ ] CI_GREEN
- [x] Rollback/limitations documented for release

## Rollback Plan

Do not deploy or run live from this worktree. For a released change, revert only the exact reviewed commit after preserving the evidence and verifying that the previous restart behavior does not violate current safety constraints. No runtime rollback action is authorized here.

## Rollout Steps

1. Resolve the source blockers: provide exact 2026-10-09 futures contract and 15:29 bar, verified 200-session daily ancestry, and an approved target-date heritage manifest; provide replay inputs with exact option identity and complete timestamp coverage or keep replay blocked.
2. Design a generation-scoped staged callback publication protocol before attempting to shorten the critical section. Preserve current stale-callback and lock-order invariants, then stress-test it and measure cutover latency under representative batch and persistence load.
3. Review and release the exact isolated worktree diff only after required CI, UAT/product acceptance, and release gates pass. Do not copy or hot-edit into an active runtime.
4. At a separately authorized later observation, require current feed truth to show fresh same-socket connect, subscriptions, and option ticks before any recovery claim; a passing offline suite is not production verification.

## Evidence

- Tests: Independent QA ran the full scoped suite with isolated temporary HOME: 275 passed, zero deselections. Developer expanded validation across changed components and adjacent heritage/observer/evidence contracts: 392 passed, zero deselections. The latest broader related suite across restart, callback, replay, evidence, launch-plan, and observer modules passed 238 tests, zero deselections. Earlier callback certification and lock-order counts above are historical and predate the queue-rejection integration test. With the actual home, an earlier cross-checkout lock test failed because the active observer owned the shared lock; isolated runs exercised and passed that test. Coverage includes fail-closed restart and generation-bound proof, offline replay boundaries and complete-horizon checks, retained rotation gap/corruption/hash/run-identity/type validation, writer-lock serialization, preservation of unknown cumulative export totals through the observer summary, stale callback rejection, and callback/startup/subscription lock ordering. These callback fixtures do not establish representative cutover latency. Python compilation and `git diff --check` passed. Pandas emitted existing numexpr/bottleneck version warnings; dependencies were not changed.
- Logs/reports: Read-only active run audit on 2026-10-12 ~15:28 IST: PID 6107/run `run-8ff3eab59881`; runtime artifact `RESTART_VERIFY_FAILED`, `feed_ok=false`, `ws_connected=false`, tick/depth age ~12,829 sec, restart allowed but not attempted, verifier `FAILED` (`tick_stalled`), and `NO_LIVE_OPTION_FEED` for BANKNIFTY/NIFTY/SENSEX. Nested recovery diagnostics report transport connected/recent callbacks but are unverified (core freshness 21/31; `core_quorum_below_threshold`), so do not certify recovery. At 15:30:50 the runtime snapshot changed to `STOPPED`/`MARKET_CLOSED` with feed still false and no option-feed proof. Its shutdown report later recorded an expired 30-second drain deadline, one runtime write pending/in-flight, and `READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE`; the processes subsequently exited. Four retained watchdog logs parsed 34,692 structured event rows, including 6,451 old-name full-path requests, 5,694 breaker-block events, and 757 concurrency-block events. These bounded-ring counts reconcile but are not lifetime counts or completed restart totals.
- Agent review evidence: Hermes contract review; Grill Me adversarial review; GSD Upstox data-path trace; senior QA, QA lock-order re-review, and full-fixset reviewer passed stale-callback, startup, and subscription-mutation lock ordering. Independent QA found the synthetic `no_hit` and boolean-as-integer validation defects; both were fixed and retested. Independent full scoped QA passed 275 tests; expanded developer validation passed 392 tests, all with zero deselections. The generation lock spans persistence/runtime snapshot work and could delay socket cutover.
- Additional callback validation: static persistence call-chain, callback filesystem tripwire, worker-thread persistence, and rejected runtime-queue checks pass. The queue rejection path no longer performs direct artifact fallback or rejection logging on the `on_ticks` callback. Non-callback direct fallback remains covered. The broader suite across restart, callback, replay, evidence, launch-plan, and observer contracts passed 238 tests with zero deselections. This does not measure production-equivalent callback-lock latency.
- Live readiness: FIX BRANCH OFFLINE-VERIFIED; PRIOR RUN NOT RECOVERED. The final 15:30:50 IST runtime artifact (SHA-256 `c6301d7c72df4fda1e80fad71ed19cbf2a44883c0e2fc0835fe8e44ed67af318`) is a historical snapshot reporting `STOPPED`, `MARKET_CLOSED`, `feed_ok=false`, `ws_connected=false`, restart disallowed, stale tick/depth ages around 12,997 seconds, and no live option-feed proof. Its shutdown artifact reports drain incomplete/deadline expired with one runtime write pending, so that session was not certified cleanly drained. A historical 15:28 read-only scan of the supplied 2026-10-12 chunk folder found 387 readable files / 3,798,279 rows, but it is same-day data and exposes no explicit instrument-type column; no symbol string contains `FUT`. The 2026-10-09 capture files did not establish required futures/SMA200 heritage. Current follow-up has a local offline manifest adapter, but no source meeting the OHLC/identity/coverage contract has been verified. Incident counts beyond the retained restart ring remain partially RTF-only; callback lock latency and a safe short-lock design remain deferred. No live restart/recovery check was performed.
- PR: None. No commit or push.
