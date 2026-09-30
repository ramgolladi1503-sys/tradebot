# MROS Live Runtime Truth Repair — Hermes Stage 1

**Date:** 2026-09-30
**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `MAP_WORKFLOW`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**Status:** Design contract for offline scoped implementation; no live validation or execution authorization.

## Objective and safety boundary

Repair feed dependency truth, runtime snapshot persistence, sampled depth accounting, websocket recovery reconciliation, MEG completed-bar synchronization, and top-level health aggregation on the isolated engineering branch. Preserve all existing fail-closed behavior and read-only boundaries. Do not change strategies, risk rules, broker/order authority, authentication, SIM/PAPER/LIVE authorization, or live process behavior.

All output/evidence must preserve:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```

No work in this scope may access a broker API or control a process. Synthetic tests prove code contracts only, not live operation.

## Scope and file inventory

Only the following paths are authorized for this implementation:

| Path | Responsibility |
|---|---|
| `core/feed_health_truth.py` | Keep global transport/runtime safety vetoes while scoping option freshness/blockers to caller-requested symbols. Expose global monitored degradation separately so unrelated stock options remain visible. |
| `core/symbol_execution_safety.py` | Pass only explicitly declared candidate feed domains into feed-truth classification; retain per-symbol quote checks and fail closed on declared missing/unknown domain evidence. |
| `core/feed/runtime_store.py` | Add bounded, observable latest-state coalescing for runtime health snapshots; preserve terminal persistence failure/degradation visibility. |
| `core/kite_depth_ws.py` | Route runtime snapshot publications through the scheduled persistence contract and strengthen required-symbol recovery evidence only where current state transitions permit proof. |
| `core/depth_store.py` | Define the existing depth capture as explicit sampled/coalesced state capture; expose input/sample/persist/reject counters and capture mode, retaining queue rejection evidence. |
| `core/feed_recovery_coordinator.py` | Require an explicit reconciliation proof before clearing recoverable websocket incident state; retain incident history and fail closed on missing/mismatched required identities, excessive gaps, or failed state rebuild. |
| `core/market_event_graph_live_runtime_bridge.py` | Apply a bounded event-time completion grace to the already-authoritative required universe; classify complete/partial/timed-out outcomes, never synthesize/forward-fill bars, and enforce a freshness cap. |
| `core/observability/sidecar_reporter.py` | Aggregate execution-plane status alongside token and lineage status; missing required status is UNKNOWN, degradation/block/unsafe states cannot be HEALTHY. |
| `config/config.py` | Add conservative explicit bounds for coalescing cadence, sampled-depth interval, recovery gap threshold, and MEG completion grace/freshness cap. Parse as finite nonnegative/positive values and fail closed on invalid settings where consumed. |
| `tests/test_edge43_feed_health_truth.py` | Assert requested-symbol scoping, global safety vetoes, and visible unrequested degradation. |
| `tests/test_edge45_symbol_execution_safety.py` | Preserve boundary that symbol-scoped observability cannot bypass candidate execution safety. |
| `tests/core/test_runtime_snapshot_store.py` | Exercise burst coalescing, bounded queue saturation, outcome accounting, and safe shutdown behavior. |
| `tests/test_kite_depth_ws_observation_on_ticks.py` | Verify callback routes observations without raw-tick loss claims or execution side effects; required recovery does not clear on transport reconnect alone. |
| `tests/test_depth_store_accounting.py` | Verify `SAMPLED_DEPTH` mode, window coalescing, persisted/rejected counts, explicit saturation degradation, and no raw-completeness claim. |
| `tests/test_feed_recovery_coordinator.py` | Verify complete proof clears; missing/extra identities, excessive gaps, incomplete rebuild, and absent proof remain blocked; incident record is retained. |
| `tests/test_market_event_graph_live_runtime_bridge.py` | Verify grace accepts a delayed completed bar, missing bar times out, no synthesis occurs, and stale/late snapshots reject. |
| `tests/test_sidecar_reporter_status_aggregation.py` | Verify all required status combinations and UNKNOWN propagation. |
| `docs/agent_reviews/MROS_LIVE_RUNTIME_TRUTH_REPAIR_HERMES_STAGE1_20260930.md` | This design, invariants, test gates, risks, and unresolved claims. |

### Stage 1 amendment — distinguish Git LFS pointer from local Parquet data

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**Scope:** `tests/test_four_strategy_dataset_manifest.py` only.

The whole-suite failure was caused by the first existing tick candidate being a 132-byte Git LFS pointer. The test must never send that pointer to the Parquet inspector or treat its file existence as data authority. Detect the canonical LFS pointer signature, continue only to another explicitly listed local data candidate, and skip with an explicit unavailable-corpus reason if no real file exists. A real Parquet candidate must still pass the existing schema/field-classification assertions. Do not fetch LFS objects or write to the canonical checkout.

Acceptance proof: a pointer followed by a real local candidate selects the real candidate; a pointer alone skips as unavailable; a byte-identical canonical local object is used read-only when present; the real data assertions remain intact. This only improves test input selection and grants no strategy, provenance, or runtime authority.

No T-1 heritage logic change is authorized. Existing heritage graph/verifier tests are regression checks only; any uncovered source-authority requirement remains explicitly unknown and fail-closed.

### Stage 1 amendment — restart-verification bypass (2026-09-30)

Forensic review found `_tick_feed_restart_verification` could clear `ws1006_process_restart_required` after subscription/option-tick verification without invoking the causal recovery coordinator. That evidence is insufficient under the invariant above. Stage 2 must retain the restart-required blocker, emit an explicit denied-clearance record, and test the exact blocker remains visible after subscription replay. This closes the bypass but does not implement a runtime causal proof builder; a subsequent clear requires complete coordinator proof or remains blocked.

Follow-up inspection found partial-activity stable-tick recovery also called the shared clear helper and reported `LIVE` without guarding a process-restart blocker. Stage 2 must make the helper refuse while a restart-required/reactor-terminal blocker is active, keep runtime status `RECOVERY_BLOCKED`, and preserve the blocker in telemetry even if local tick activity verifies. Stable local activity is not causal restart recovery proof.

### Stage 1 amendment — callback burst admission replay (2026-09-30)

Add an offline regression that invokes the actual `on_ticks` callback with two consecutive 855-row synthetic batches while the runtime snapshot interval is 60 seconds. Assert every valid row reaches tick and depth-observation instrumentation and that expensive runtime snapshot assembly/publication is admitted once and coalesced once. Keep external persistence/forensic effects stubbed; this proves callback ordering and bounded snapshot assembly only, not production throughput, durable raw-tick completeness, or live runtime performance. No live process, broker, order, or risk behavior is in scope.

### Stage 1 amendment — canonical feed truth fixture evidence (2026-09-30)

The whole-suite failure list includes a canonical runtime-artifact test that expects LIVE while its synthetic payload omits per-symbol option-age evidence. The classifier intentionally treats a missing requested/monitored option age as unknown. Stage 2 may update only that fixture to provide an explicit fresh NIFTY option age, leaving all behavior assertions intact. This is a test-authority correction; no runtime fallback or health rule may be added to satisfy the old fixture.

Authorized file inventory addition: `tests/test_feed_00_canonical_feed_truth.py` — supply explicit fresh option-age evidence in the existing canonical LIVE fixture and retain the complementary missing-tick fail-closed test.

### Stage 1 amendment — snapshot scheduler audit (2026-09-30)

The prior evidence draft incorrectly stated that no independent timer scheduler existed. Source inspection confirms `_watchdog` runs a timed loop (`FEED_WATCHDOG_POLL_SEC`, minimum 0.5 seconds) and calls `_emit_snapshot` after the wait independently of `on_ticks`. This is an existing watchdog-owned timer path, not a new scheduler added by this repair. Keep the callback admission gate and prove structurally that periodic watchdog snapshot emission remains reachable after the timer wait. Do not claim production throughput from this source-level contract.

### Stage 1 amendment — recovery history immutability and identity authority (2026-09-30)

Coordinator history currently contains nested proof dictionaries. Both ingress and egress must use defensive deep copies so consumers cannot alter recorded evidence through shared nested objects. Add adversarial tests that mutate both the originally supplied proof and a returned history snapshot.

Do not build runtime recovery clearance from `_LAST_TOKENS` or `_INTENDED_TOKENS` alone. Those lists describe subscriptions, not the causal dependency set required by a consumer; treating every subscribed option as required would allow unrelated illiquid contracts to govern unrelated recovery. Runtime recovery stays blocked until an authoritative required-identity contract is available. Reconnect, subscription, and tick activity alone cannot clear it.

### Stage 1 amendment — bounded runtime recovery proof (2026-09-30)

Further inspection found the runtime already resolves the exact underlying spot token set (`_UNDERLYING_TOKENS` with `_UNDERLYING_TOKEN_TO_SYMBOL`), performs option verification per required symbol, and candidate readiness can separately check exact option token freshness. Use those distinct contracts rather than treating every subscribed option as a recovery dependency.

For recoverable peer-drop recovery only, capture the pre-disconnect receipt timestamp for every resolved underlying token, then require: exact expected-vs-locally-applied subscription set reconciliation; a first post-reconnect receipt for each required underlying token; finite gap within `FEED_RECOVERY_MAX_GAP_SEC`; successful per-symbol option verification when applicable; websocket connected; runtime safe; and a configurable consecutive healthy window. If the resolved underlying set is empty, any required pre-timestamp is absent, subscription sets differ, or any proof field is unavailable, retain the recovery block. Reactor-terminal/process-restart-required blockers are never cleared by this in-process proof. Candidate exact-option freshness continues to be enforced at the consumer boundary.

## Invariant contracts

### Feed health

1. `symbols=(...)` is an explicit dependency set. Per-symbol option age/block reasons outside that set do not make that requested dependency decision false.
2. `feed_ok=False` derived solely from an unrelated optional symbol is not sufficient to veto the requested dependency set. Global disconnection, unsafe runtime/feed state, stale required underlying/depth evidence, and explicit global critical faults remain blocking.
3. Unrequested degraded symbols remain included in a structured monitored-health summary; omission from the decision does not relabel them healthy.
4. No freshness threshold is widened by this work.
5. Missing requested symbol evidence is UNKNOWN/BLOCKED, not inferred healthy.

### Runtime snapshot persistence

1. Snapshot persistence is latest health/state metadata, not raw tick capture. Coalescing only replaces older snapshots with the same explicitly defined identity/key.
2. Queue and pending coalesced state remain bounded. Saturation, serialization/write failure, and shutdown rejection are accounted and visible; no drop is silent.
3. Expose monotonic counters: requested, coalesced, enqueued, persisted, rejected, queue high-water mark, and writer lag. Counters must reconcile with the documented state transitions.
4. Preserve current durable write path and canonical artifact lineage. Never claim a snapshot persisted before sink completion.
5. Default cadence is configuration-driven and chosen to be no faster than current state-read/write requirements; this is not a feed freshness threshold.

### Depth capture

1. Existing `DepthStore.update` persistence is sampled/coalesced state capture; it is not a lossless raw websocket event ledger. Label this explicitly as `SAMPLED_DEPTH` in status/evidence.
2. Track raw updates observed, sample windows accepted, snapshots persisted, updates coalesced, and persistence rejects. A saturated or failed sink is degraded and auditable.
3. Do not report `PARTIAL_DEPTH` as complete or call sampled records raw/lossless.
4. No queue-size-only remediation and no swallowed failure.

### Websocket recovery

1. A reconnect or resumed tick is not recovery proof.
2. Recovery may clear only with an explicit proof containing incident identity/generation, exact required token identities, expected and actual subscriptions, pre/post timestamps and computed gap per required identity, successful state rebuild, and a bounded health-window result.
3. Missing or extra required subscription identities, non-finite/invalid/future timestamps, non-finite or over-bound gaps, missing rebuild proof, absent explicit healthy-window status, or a verdict other than `RECOVERED` keep the coordinator blocked/unverified.
4. Successful reconciliation appends resolution metadata to the in-memory coordinator history; original incident fields are not erased from history.
5. No code removes or rewrites restart-required artifacts in this scope.

### MEG event-time completion

1. The required universe and identity/provenance checks remain authoritative.
2. For target bar close `T`, wait at most the configured grace for every required completed bar at exactly `T`.
3. All present and valid at deadline-before/at completion => COMPLETE; deadline with some valid identities absent => TIMED_OUT; present but incomplete/misaligned evidence => PARTIAL/rejected. No synthetic bars, forward fill, or future timestamps.
4. Emit only when completed source time satisfies the configured maximum decision freshness. Grace cannot extend usable decision age beyond that cap.
5. Rejections remain explicit and include missing identities and completion latency.

### Top-level status

1. Overall state is derived from token, pipeline, and supplied execution-plane truth. Required execution-plane state absent => UNKNOWN (except where no execution-plane contract is requested by a legacy caller; compatibility must not claim overall HEALTHY when required fields are absent).
2. UNSAFE safety invariant violation has highest precedence, then BLOCKED, then OPERATIONAL_DEGRADED, then UNKNOWN, then HEALTHY only when all required observed states explicitly pass.
3. PID presence, tick progress, candidate count, and default values never prove overall health.
4. Existing safety-boundary output remains false for every authority field.

## Implementation sequence

1. Add this contract and focused behavior tests before changing production logic.
2. Fix feed classification while preserving global transport/safety checks.
3. Add runtime persistence coalescing and state accounting; wire the callback snapshot publications.
4. Add explicit sampled-depth accounting to the existing `DepthStore` persistence path.
5. Add proof-gated recovery clear while retaining `clear_recovery` compatibility only if it cannot be invoked without proof in runtime paths; otherwise fail closed and update in-scope callers/tests.
6. Add MEG completion grace using the injected/monotonic clock pattern where possible; test without wall-clock sleeps.
7. Aggregate sidecar status with explicit precedence and UNKNOWN behavior.
8. Run only focused offline suites and existing heritage regression tests; parent performs independent final validation and creates the evidence package.

## Acceptance tests

| Area | Required proof |
|---|---|
| Feed | Unrelated stale stock option + global derived degraded flag does not block an explicitly healthy NIFTY dependency set; required stale/missing option blocks; websocket down/unsafe runtime blocks; unrelated degradation is returned visibly. |
| Runtime snapshots | A burst for one identity coalesces to newest state; multiple identities remain distinct; injected queue-full/write-fail/shutdown paths increment rejected/degraded state; requested/coalesced/enqueued/persisted/rejected counters reconcile. |
| Depth | Burst updates yield explicit sampled count/coalesced count; forced sink saturation/failure is rejected and visible; payload labels `SAMPLED_DEPTH`, never raw complete. |
| Recovery | Exact complete required token set + acceptable gaps + rebuilt state + health window returns RECOVERED; missing/extra identity, over-bound gap, unknown timestamps, absent rebuild, or missing proof cannot clear; incident history remains available. |
| MEG | A completed required bar arriving at 700 ms within grace can complete; a required bar missing for 20 seconds times out; no synthesized/forward-filled rows; a completed but stale bar is rejected. |
| Status | Healthy only when every required status is explicit healthy; websocket/queue degraded => degraded; heritage/candidate blocked => blocked; invariant violation => unsafe; missing subsystem => unknown. |
| Safety | All tests assert read-only, no order action, no broker API call, and no live execution authorization. |

Focused command plan:

```bash
pytest -q tests/test_edge43_feed_health_truth.py tests/test_edge45_symbol_execution_safety.py
pytest -q tests/core/test_runtime_snapshot_store.py tests/test_kite_depth_ws_observation_on_ticks.py
pytest -q tests/test_depth_store_accounting.py
pytest -q tests/test_feed_recovery_coordinator.py
pytest -q tests/test_market_event_graph_live_runtime_bridge.py
pytest -q tests/test_sidecar_reporter_status_aggregation.py
pytest -q tests/test_market_heritage_graph.py
```

The checkout contains `tests/test_market_heritage_graph.py`; there is no separate `tests/test_market_heritage_verifier_independent.py`. The graph suite includes independent manifest-verification assertions. No live entrypoint or broker/API test is allowed.

## Configuration contract

Candidate keys to define only when existing code has no equivalent:

```text
FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC
FEED_RUNTIME_SNAPSHOT_COALESCE_MAX_IDENTITIES
DEPTH_CAPTURE_MODE                 # fixed to SAMPLED_DEPTH; not an operator switch to lossless
DEPTH_SAMPLE_INTERVAL_MS
FEED_RECOVERY_MAX_GAP_SEC
MEG_COMPLETION_GRACE_MS
MEG_MAX_DECISION_FRESHNESS_SEC
```

Bounds must be validated at use. Invalid values fail closed or fall back only to a documented conservative constant that still preserves current safety semantics. No env/config value may authorize execution or weaken freshness/risk gates.

## Risks and unresolved requirements

- The true production runtime snapshot identity and required persistence cadence must be verified from all in-scope writers; coalescing across distinct feeds/sessions would be data corruption.
- Existing depth storage is state-oriented and batched, but data consumer expectations still need to be checked. This change can truthfully certify sampled-state accounting only; it cannot establish lossless raw capture.
- The existing recovery coordinator is currently a pure state machine and has direct `clear_recovery` calls in tests/callers. Runtime integration must be found within the authorized paths. If reconciliation proof cannot be fed to the actual caller without editing forbidden files, stop and report rather than claim production recovery is fixed.
- The MEG bridge may be invoked synchronously; blocking grace can increase decision latency. The freshness cap must be lower than the consumer's existing stale cutoff or the fix is not acceptable.
- Sidecar callers may omit execution-plane state. UNKNOWN is honest, but could alter reports. Preserve schema and explain migration.
- The requested baseline test fixture isolation may involve `tests/conftest.py`, which is outside this implementation allowlist; do not change it. If contamination invalidates results, report it and isolate runs by fresh process.
- T-1 source readiness, live causality, and Antigravity non-interference cannot be established by synthetic tests. No live readiness or production-ready claim is permitted.

## Migration and run notes

No database schema migration is expected. New counters and mode/status fields are additive. Existing sidecar consumers should treat new unknown/degraded states as non-healthy. Operators must leave all new safety-related bounds at conservative defaults until reviewed. Run focused tests above in the designated offline worktree only. Parent creates and hashes the evidence package after independent final validation.

## Controlled verdict

The only valid outcome from this work is offline implementation/test status (`IMPLEMENTATION_VALIDATED_OFFLINE`, `PARTIALLY_VALIDATED`, or a specific blocked/inconclusive verdict). This contract does not authorize or establish live verification, execution viability, strategy validity, certification, profitability, or production readiness.

## Stage 1 amendment — producer-side cadence gate

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/feed/runtime_store.py`, `core/kite_depth_ws.py`, `tests/core/test_runtime_snapshot_store.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`.

The queue cadence alone does not bound callback-side snapshot assembly. Add a producer admission gate before expensive DB/depth/status collection. Count every producer request and cadence-coalesced request separately from queue admission counters. For `source == "on_ticks"`, suppress only when the safety-relevant producer identity is unchanged and the configured interval has not elapsed. Include session/boot/feed/recovery generation, websocket and runtime states, auth/restart/recovery blockers, disconnect cause, and restart/option-verification state. Any identity change must pass immediately. Non-tick lifecycle sources always pass. This gate controls only health-snapshot assembly and does not skip, coalesce, or alter raw tick/depth evidence.

Acceptance proof: a repeated same-identity tick callback within cadence does not invoke full snapshot assembly; a transition in each included safety field passes immediately; after cadence expiry the latest callback assembles/publishes; lifecycle calls always pass; producer and queue counters remain separately reconcilable. The existing watchdog artifact path remains independent. This bounds producer work but is not a separate timer-driven snapshot scheduler or production load proof.

## Stage 1 amendment — isolate startup test launch-plan authority

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `tests/test_feed_runtime_states.py` (single startup test only).

The scoped combined regression exposed shared test-process launch-plan state: an earlier test leaves an enabled 55-token plan, while `test_start_depth_ws_writes_import_missing_state` asserts behavior for its explicit two-token input and an absent plan. Make that test explicitly provide no active launch-plan tokens. Preserve its intended-token assertion and production launch-plan precedence. Do not modify `conftest.py` or production launch-plan behavior.

## Stage 1 amendment — partition spot-domain evidence by explicit symbol identity

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/kite_depth_ws.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_edge43_feed_health_truth.py`.

The runtime producer already maps each underlying spot token to its requested symbol and has the authoritative index-symbol set. Partition mapped identities into `INDEX_SPOT` and `STOCK_SPOT` before reducing health. A stale or missing equity spot must not turn a healthy index-spot domain into UNKNOWN; it remains visible as stock-spot degradation/unknown. An unmapped underlying identity must remain UNKNOWN in the monitored stock-spot domain rather than be guessed as an index. Continue to leave `INDEX_FUTURES` UNKNOWN because this producer has no explicit futures contract identity source. Reuse the existing strict spot-age bound; do not widen freshness.

Acceptance tests: mixed NIFTY and TCS identities with fresh NIFTY and stale TCS produce `INDEX_SPOT=HEALTHY`, `STOCK_SPOT=DEGRADED`; an index-only consumer requiring healthy index domains remains allowed while overall health reports degradation; missing/invalid identity evidence remains UNKNOWN.

## Stage 1 amendment — prevent positive inference of missing feed truth

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/observability/sidecar_reporter.py`, `tests/test_sidecar_reporter_status_aggregation.py`.

Token health may add negative feed-truth evidence (`BLOCKED` for system critical, `OPERATIONAL_DEGRADED` for degraded/partial), but a token-health `HEALTHY` result cannot satisfy a missing required `feed_truth` subsystem. Top-level HEALTHY requires explicit execution-plane feed truth and every other required subsystem. Add an adversarial test with healthy token health and missing feed truth; expected overall state is UNKNOWN.

## Stage 1 amendment — pass explicit candidate feed dependencies to safety classification

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/symbol_execution_safety.py`, `tests/test_edge45_symbol_execution_safety.py`.

Inspection found that `classify_feed_health_truth` accepts `required_domains`, but the candidate safety consumer did not pass any. Read optional `required_feed_domains` from the candidate or its `source_flags`; pass it to classification and preserve the declared dependency set in decision context. Do not infer dependencies from strategy family, symbol name, token counts, or defaults. An explicitly supplied unknown/invalid domain remains fail-closed through the classifier. Preserve existing per-symbol quote/feed checks when no dependency declaration is supplied; this change does not populate declarations in candidate generators or alter strategy definitions. Producers must supply authoritative dependencies before domain gating applies to those candidates.

Acceptance: explicit healthy NIFTY domains remain allowed while unrelated stock domains are degraded; declared unknown/missing `INDEX_FUTURES` blocks; stale selected-symbol option evidence still blocks; source-flag declarations are propagated; no dependency declaration is fabricated. No broker or order path is added.

## Stage 1 amendment — require exact T-1 target session identity at consumption

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/market_heritage_graph.py`, `tests/test_market_heritage_graph.py`.

The pinned-manifest loader currently checks only that every caller-supplied target-session field matches the manifest. A caller can omit calendar identity fields and still consume a manifest; the manifest can also carry extra session fields outside the caller's target identity. Require exact mapping equality between the verified manifest session identity and caller target session. Do not synthesize missing identity fields. Return BLOCKED with `TARGET_SESSION_MISMATCH`; values remain empty. Acceptance covers incomplete caller identity and an extra manifest identity key while all existing valid exact-session loads remain valid.

## Stage 1 amendment — fail closed when domain evidence lacks candidate dependencies

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/symbol_execution_safety.py`, `tests/test_edge45_symbol_execution_safety.py`.

The candidate consumer can receive structured `domain_health_by_domain` from runtime feed evidence, while the candidate producer currently supplies no required-domain declaration. Passing such a candidate using only symbol-level quote freshness would leave the domain contract bypassable. When structured domain evidence is present, a candidate must carry a nonempty explicit `required_feed_domains` list at the candidate or source-flag boundary; missing, empty, malformed, or invalid declarations block execution with a visible reason. Do not infer domains. Legacy symbol-only payloads without structured domain evidence retain existing per-symbol checks. A producer must add authoritative dependency declarations before those candidates can pass with structured domain evidence.

Acceptance: structured domains + absent/empty/malformed dependencies block; a declared healthy index dependency set passes while unrelated stock degradation remains visible; unknown required domains block; legacy symbol-only compatibility remains covered.

## Stage 1 amendment — provide truthful feed evidence in executable-truth fixture

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `tests/test_executable_truth_firebreak.py`.

The combined regression found its nominally clean candidate has a symbol but no per-symbol feed age/blocker or transport evidence; the production classifier correctly blocks it as unknown. Preserve the behavior assertion and add explicit fresh selected-symbol feed and connected-transport evidence to the clean fixture. Do not change production safety behavior or remove/relax any assertion. Failure-injection cases continue to override relevant fields and prove the designated blocker.

## Stage 1 amendment — exercise sampled-depth 855-row sink drain and exact interval metric

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/depth_store.py`, `tests/test_depth_store_accounting.py`.

The 855-token sampled-depth replay currently proves queue admission only; the acceptance requires persistence accounting. Add a deterministic offline test that sends one sampled record per 855 distinct tokens through the actual DepthStore writer into a temporary SQLite database, drains it, queries the persisted rows, and asserts zero reject/failure plus exact reconciliation. Also ensure the reported sampling interval preserves an explicit configured zero instead of replacing it with a 500 ms fallback; production default remains unchanged.


## Stage 1 amendment — reject invalid depth sampling interval

**Source agent:** `hermes`
**Allowed actions:** `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`
**Scope:** `core/depth_store.py`, `tests/test_depth_store_accounting.py`.

A negative or non-finite `DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC` currently collapses to zero, disabling sample coalescing. Validate at use: retain finite nonnegative intervals (including explicit zero for deterministic/offline compatibility), use the documented 0.5-second conservative default for negative/non-finite/unparseable settings, and surface invalid configuration in persistence telemetry with degradation evidence. Test NaN and negative values. Do not change the normal 0.5-second configured default.

## Stage 1 amendment — governed candidate dependency declarations and config immutability

**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**Scope:** new declarative `core/candidate_feed_dependencies.py`; `core/symbol_execution_safety.py`; `core/feed_health_truth.py`; `core/kite_depth_ws.py`; focused dependency/safety/feed-health tests; reliability settings module and existing repair consumers/tests listed below. This amendment authorizes design only; it does not authorize source or test changes.

### Evidence and problem statement

The continuation dependency inventory is explicitly `PARTIAL / BLOCKED`. It identifies some source-backed consumers/declarations, but also unknown strategy families, missing exact futures identity, and broad domain aggregation. Do not convert that inventory into a complete dependency map by guessing from strategy names, symbols, token subscriptions, or `EQUITY_INDEX_OPTIONS` labels.

`classify_symbol_execution_safety` consumes candidate-supplied `required_feed_domains`; with structured domain health it blocks candidates lacking a declaration. This is a useful fail-closed boundary, but it neither resolves an immutable candidate identity against a governed registry nor provides exact instrument-scoped health. `classify_feed_health_truth` recognizes only the fixed coarse domains `INDEX_SPOT`, `INDEX_FUTURES`, `INDEX_OPTIONS`, `STOCK_SPOT`, and `STOCK_OPTIONS`. The runtime producer still reports futures identity as unavailable/UNKNOWN and aggregates members at domain level. Therefore a domain declaration is not proof that the candidate's exact required contract or quote is healthy.

The current repair also appended seven reliability settings to `config/config.py`. `tests/test_c1_c2_regime_decoupling.py::test_regime_source_immutability_audit` includes that file in a pinned SHA-256 and byte-length allowlist. The current file consequently violates an explicit byte-for-byte invariant, even though the appended settings are unrelated to regime logic. Do not weaken the test, update its expected digest, or describe the failure as merely unrelated.

### Candidate dependency contract

1. Define a repository-owned, immutable declarative registry keyed by an exact canonical candidate/consumer ID. Every admitted entry must carry `authority_status`, source path(s) and immutable source digest(s), plus separate `required_domains` and `required_identities` fields. Keep evidence refs and status visible in the resulting safety decision. This is a data contract, not permission to change strategy rules or runtime behavior.
2. Distinguish `VERIFIED_DECLARATION`, `PARTIAL_DECLARATION`, and `UNKNOWN_BLOCKED`. A registry entry with unknown or partial required inputs must not become executable merely because one known domain is healthy. Unknown IDs, absent IDs, duplicate IDs, malformed schemas, unknown enum values, and stale/mismatched authority digests fail closed when governed lookup is required.
3. Record only dependencies proven by the inspected source/spec and the actual consuming adapter. Preserve source distinctions: advisory-only CAS is not an execution candidate; terminally frozen or historical shadow specs do not grant current execution authority; coarse `StrategyContract` labels stay coarse. Do not treat strategy family registries or generator names as dependency authority. Do not promote `DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION` without a proven current runtime registry and consumer.
4. Keep domain declarations as coarse prerequisites only. Required identity checks must be a separate contract, and are usable only when the producer supplies authoritative canonical instrument identity and matching identity-scoped freshness/block evidence. Missing/mismatched identity evidence blocks. Do not synthesize futures identity or equate a symbol alias with an instrument identity. Where the runtime can establish only domain health, report that limitation and do not claim exact candidate readiness.
5. Candidate payloads cannot widen, replace, or contradict registry dependencies. Once an exact candidate ID is known, derive requirements from the registry and reject caller declarations that differ; unknown candidate IDs remain blocked. If compatibility requires unregistered legacy payloads, limit that path to symbol-only behavior without structured domain evidence, preserve its current fail-closed per-symbol checks, and expose an explicit legacy/unresolved status. Do not let this compatibility path count as registry coverage or live readiness.
6. Registry validation must be deterministic and read-only. It must not inspect subscriptions and infer dependencies, contact brokers, alter feeds, authorize orders, or change SIM/PAPER/LIVE state. Maintain `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, and `append=false` for read-only evidence.

### Config immutability contract

Restore `config/config.py` byte-for-byte to the pinned source so the existing SHA and byte-count immutability test passes unchanged. Put the repair's newly introduced settings in a dedicated reliability settings module (proposed `config/feed_runtime_reliability.py`) and update only the repair consumers to import/use that module: `core/feed/runtime_store.py`, `core/feed_recovery_coordinator.py`, `core/kite_depth_ws.py`, `core/market_event_graph_live_runtime_bridge.py`, and `core/depth_store.py` where it reads the newly introduced capture-mode setting. Do not duplicate configuration ownership or keep shadow values in `config/config.py`.

Preserve default values and validation/failure behavior currently specified by the repair. Keep `DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC` in its existing owner because it predates this repair and is not among the appended settings. The new module must preserve the existing environment variable names and parse behavior for the new knobs; no silent fallback or relaxed gate is allowed. This migration is backward-compatible for deployed configuration because the environment variable names/defaults do not change, but it is an internal Python import-path change for these newly introduced attributes. Search for all consumer and test monkeypatches before migration. Update those monkeypatches to target the new settings owner; do not reduce their behavioral assertions or alter the pinned hash test. Existing external code that imported these repair-only attributes directly from `config.config` must be inventoried; if such consumers exist and byte immutability forbids a forwarding shim there, stop and document the compatibility conflict rather than silently break them.

### Proposed implementation file inventory (Stage 2 only)

| File | Purpose |
|---|---|
| `core/candidate_feed_dependencies.py` (new) | Exact-ID registry, schema validation, provenance binding, and explicit unknown/partial states; no runtime side effects. |
| `core/symbol_execution_safety.py` | Resolve governed candidate IDs, compare caller declarations against authority, fail closed for unknown/mismatch, and retain honest coarse-vs-identity-scoped limits in decision context. |
| `core/feed_health_truth.py` | Validate and classify explicit identity-scoped evidence only if that evidence contract is actually supplied; retain existing domain classifier semantics and UNKNOWN for missing identity evidence. |
| `core/kite_depth_ws.py` | Only if source-backed identity production can be implemented from current authoritative token/contract mappings; otherwise leave futures identity UNKNOWN and explicitly defer this file. Never infer a contract key. |
| `config/feed_runtime_reliability.py` (new) | Own the newly introduced repair-only settings and environment parsing without touching pinned `config/config.py`. |
| `core/feed/runtime_store.py`, `core/feed_recovery_coordinator.py`, `core/market_event_graph_live_runtime_bridge.py`, `core/depth_store.py` | Import the new settings owner for the corresponding new settings; preserve existing defaults and explicit validation. `depth_store.py` continues reading its pre-existing interval from `config.config`. |
| `tests/test_edge45_symbol_execution_safety.py`, `tests/test_edge43_feed_health_truth.py`, `tests/test_kite_depth_ws_observation_on_ticks.py` | Registry, unknown/mismatch, identity-scoped health, and broad-domain limitation behavior proofs. |
| `tests/core/test_runtime_snapshot_store.py`, `tests/test_feed_recovery_coordinator.py`, `tests/test_kite_depth_ws_stability.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_market_event_graph_live_runtime_bridge.py`, `tests/test_depth_store_accounting.py` and any other exact `rg`-identified monkeypatch sites | Retarget config monkeypatches to the new settings module while preserving every existing behavior assertion. |
| `tests/test_c1_c2_regime_decoupling.py` | No change authorized or required; its current pinned `config/config.py` digest and byte count remain unchanged and must pass. |

The inventory is conditional: identity-scoped runtime production is not yet proven. Before Stage 2, enumerate all relevant import and monkeypatch sites and compare current environment-config compatibility. If exact dependencies or canonical identity authority remain absent, keep those candidate entries blocked and do not fabricate a passing test fixture.

### Acceptance proof required before this repair can claim dependency authority

- Registry tests cover known exact IDs, provenance digest mismatch, unknown IDs, absent/duplicate IDs, malformed declarations, partial/unknown authority, and caller attempted widening/narrowing/mismatch. All unresolved cases block with stable machine-readable reasons.
- For each admitted candidate, a table-driven test binds its declared source-backed dependencies to registry output. Historical/advisory entries remain non-executable; unknown strategy families remain blocked.
- Domain-only evidence cannot satisfy a required exact identity. Missing, stale, mismatched, or extra/unrelated identity records do not produce a positive identity-scoped result. A healthy exact identity may pass only while all existing global/runtime/websocket and per-symbol fail-closed checks still pass.
- Existing broad domain tests continue to prove unrelated degradation remains visible and cannot be represented as exact instrument health. `INDEX_FUTURES` remains UNKNOWN until a real authoritative producer is identified and tested.
- Preserve all current feed, recovery, persistence, callback, and lifecycle acceptance assertions after the config-module move. Environment defaults and existing environment variable names remain stable. Invalid configuration remains visibly invalid/degraded or fails closed; it is never silently accepted as healthy.
- Run `tests/test_c1_c2_regime_decoupling.py::test_regime_source_immutability_audit` unchanged and show the pinned `config/config.py` digest and byte count match. Do not update the digest fixture.
- Run the scoped repair regression and relevant monkeypatch tests in a fresh process. Then perform a full-suite run to completion or classify each failure against an exact clean-base run; an interrupted run is not a pass.

### Risks and unresolved items

- Candidate IDs in generated runtime payloads may not map one-to-one to the candidate/spec names in the inventory. This must be demonstrated from producer and consumer code before adding a registry entry.
- Current domain aggregation is too coarse to prove exact option/futures contract health. If exact identity production is not in this patch's authorized scope or cannot be source-backed, dependency readiness remains BLOCKED. Do not make identity-scoped health a synthetic fixture-only feature.
- The new config attributes were introduced by this repair, but direct Python imports outside this repository may exist. Preserve env-level compatibility; inventory internal imports and explicitly report any unresolved Python import compatibility before migration.
- This amendment does not certify live readiness, permit strategy/risk/broker changes, authorize order actions, or assert that the current repair is fixed. Stage 2 implementation and complete validation remain outstanding.

## Agent Work Contract

- `source_agent`: Hermes design record or GSD scoped execution record as declared above.
- `action`: design/contracts/acceptance gates for Hermes; scoped implementation/tests/evidence for GSD.
- `scope`: offline MROS runtime truth and candidate-dependency safety only.
- `requested_paths`: the files explicitly named in this record and its linked implementation.
- `allowed_paths`: associated runtime-truth modules, tests, design notes, and the repair evidence package.
- `forbidden_paths`: credentials, environment files, live runtime data, broker write paths, order actions, and strategy thresholds.
- `expected_tests`: focused feed-health, symbol-safety, recovery, heritage, dependency-registry, or write-guard tests named in the evidence package.
- `acceptance_proof`: deterministic offline tests pass; unsafe or incomplete authority remains blocked.

## Scope Guard

This record covers offline implementation and verification only. It grants no order, broker, paper, live, credential, or strategy authority. Candidate declarations require exact source identity; missing facts remain UNKNOWN/BLOCKED.

## Grill Me Review

The principal risk is overstating synthetic, coarse-domain, or partial evidence as feed authority. The registry and consuming boundary must retain visible block reasons; tests must exercise the actual safety decision.

## Hermes Review

The contract separates candidate identity, required domain, canonical identity, freshness authority, execution scope, and unresolved evidence. A partial or unknown declaration cannot become eligible through caller-provided health alone.

## GSD Review

Execution stays within the declared files. Regression tests cover both accepted safe cases and fail-closed missing/mismatched authority. No live runtime wiring, strategy change, broker call, or order action is part of this work.

## QA / Safety Review

The current-tree whole-repository offline suite passed 8,493 tests (9 skipped, 28 deselected); the focused candidate/feed/symbol/heritage/T-1 suite passed 118 tests. These results prove test behavior only, not production runtime readiness.

## Acceptance Proof

See `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/FINAL_CONTINUATION_VERDICT.md`, `TEST_RESULTS.md`, `MANIFEST.json`, and the adjacent SHA-256 checksum list. The candidate registry has 14 exact IDs, 23 unknown/unverified labels, and zero execution-eligible candidates.

## Runtime Proof Required After Merge

No runtime proof is asserted. Any future runtime validation requires a separately authorized, read-only, non-ordering procedure with exact process, source-event, identity, freshness, and artifact bindings. Live execution remains unauthorized.

## What This PR Does Not Prove

It does not prove complete candidate dependency coverage, T-1 provenance, production throughput, live process continuity, broker behavior, or execution readiness. Missing authority remains a blocker.

## Human Approval

This PR was opened under the user's explicit goal to reach a merge after fixes and green CI. That authorization does not grant live, paper, broker-write, order, or strategy-change authority. Merge remains gated on required CI and repository policy.

## High-Risk Path Review

Changed feed/WebSocket/runtime-safety paths were reviewed for fail-closed behavior. Changes add identity-bound admission/accounting and recovery proof requirements; they do not weaken freshness, risk, kill-switch, or order gates. Focused negative tests cover missing, stale, mismatched, and opaque authority. Production behavior remains unverified.
