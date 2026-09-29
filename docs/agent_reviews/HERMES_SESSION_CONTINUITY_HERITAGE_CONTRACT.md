# Hermes: Cross-Day Session Continuity and Heritage Contract

Status: FROZEN DESIGN / IMPLEMENTATION BOUNDARIES

- source_agent: hermes
- action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
- title: Immutable same-day and cross-session heritage for read-only strategy readiness
- requested_paths: core/cas_primitive_producer.py; new core/market_heritage_graph.py; tests/test_market_heritage_graph.py; tests/test_cas_primitive_producer.py; docs/agent_reviews/ (evidence and design)
- allowed_paths: dedicated worktree only; no canonical checkout edits
- forbidden_paths: broker/order/risk/feed authority changes; strategy thresholds/contracts; credentials/env; raw runtime evidence; execution/entry-authority behavior
- expected_tests: graph identity/hash/edge/cycle/conflict/temporal/atomic/restart mutation tests; CAS timestamp boundary regression; current targeted existing regressions
- acceptance_proof: offline tests plus independent graph verifier; real source-dependent gates remain UNKNOWN/BLOCKED unless exact immutable source evidence closes them

## Repository and source archaeology

Inspection checkout: `ab229d3e32f5f6ceb02c476efdd53253aa55ee83` (detached isolated worktree). Canonical checkout was dirty and remains untouched. The separate worktree has no initial modifications.

Existing infrastructure: `core/read_only_live_evidence.py` provides canonical JSON hashing, append-only JSONL, and atomic replace helpers. `core/session_calendar.py` models session hours and weekends but does not establish historical venue holidays or exceptional sessions. Existing strategy T-1 facts load from launch plans, disk files, and environment variables without graph provenance. The observation runtime creates a CAS store scoped to `run_id`, explaining why a later process has no earlier-run values; this is a continuity gap, not proof earlier evidence should qualify.

Frozen inputs inspected (SHA-256):

- `docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json`: `10087e1166d8e11cde194960707e3b490d0ca30ec1df9f30bc3c42889c77cc0b`. Exact prior regular-session 15:29 bar, NIFTY futures-only, strict prior/current futures key equality, fail closed.
- `docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json`: `3e60d58c9caaa28d72fb1a79553c477cab4cd27f4d2ed27c66c4a392da1a4b7a`. Daily NIFTY50 close T-1 > SMA200 T-1, cutoff 15:20 IST; NaN fails closed.
- `docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json`: `eed4ceed76a593bb253fa795558d1a185ae0f0c698b2686d31b4be680c889d32`. Same daily NIFTY50 close/SMA200 T-1 requirement plus Monday rule.
- CAS producer `SPEC_ID=CAS_MORNING_REVERSAL_SHORT_HORIZON_PRIMITIVE_SPEC_V1`, hardcoded SHA `6567c832f26976d6a4ff71e2532dd125bf09888324e463750a8817c094b7bb6c`; frozen contract selects the validated exchange timestamp at/after target with at most 2,000 ms lateness and retains receive time separately. It does not require receive time to equal event time. The producer/verifier must bind selected time to source event time and payload while retaining receive time as its own clock.

## Observed evidence (read-only; raw files unchanged)

Exact roots inspected were the four run directories below; no arbitrary drive scan was performed.

- Later run `/Volumes/TradeBotData/sessions/session_2026-09-29/2026-09-29/meg-live-2026-09-29-4533aa1ab52b-f0aa2c226d8e`, CAS file SHA-256 `71d63f5d` (full digest recorded in source manifest): both 09:15 and 10:00 rows are `BLOCKED`, null price and all epochs, authority `UNKNOWN`.
- Earlier run `/Volumes/TradeBotData/sessions/session_2026-09-29/2026-09-29/meg-live-2026-09-29-d3c500333920-98146571ce5a`, CAS file SHA-256 `7f1d659d0b29affc6f616305103d7efffe13e2f28f4488bc15c6305e08d2b7b2`. 09:15 has exchange source epoch 1790653499.0 (09:14:59 IST), selected/receipt epoch 1790653500.028779 (09:15:00.028 IST), price 22732.45. 10:00 has source epoch 1790655435.0 (09:47:15 IST), selected/receipt 1790656201.588022 (10:00:01.588 IST), price 22607.55. The producer's current verifier rejects source/selected inequality. Its stored `lateness_ms` reflects selected epoch, which is insufficient evidence of source-event timing. `strategy_observations.jsonl` records exact `CAS_PRIMITIVE_0915_TIMESTAMP_BINDING_INVALID`.
- Prior eligible date 2026-09-28 has two run folders. First run's CAS artifact was absent; second run's CAS artifact SHA-256 `f6c4abc78c63277d642579b82ca3ecc352c080d930b276571fef48f15500cc9b`, with both rows `BLOCKED` and null source epochs/prices. Neither is eligible for same-day inheritance.
- 2026-09-28 presession manifests assert session date and read-only/no-order authority but do not seal the full source files or prove the frozen T-1 strategy values. Required exact futures 15:29 bar, matching contract key, 200-session daily series, calendar closure, and independent formulas were not established here. T-1 readiness is `BLOCKED_SOURCE_EVIDENCE`.

## Frozen data and timestamp law

1. Keep source event time, selected/freshness time, local receive time, and decision/as-of time distinct. Store original raw timestamp precision and source field. Do not infer equality from receipt timing.
2. A carried market fact binds to a specific raw source event or immutable dataset row by durable ID/hash, instrument/contract, venue, trading date/session, value/unit, producer/schema/contract version, and source-event epoch/precision. A selection rule must explicitly state whether it is event-time or receipt-time based.
3. For CAS 09:15/10:00, no source-to-price binding contract that legitimizes the observed mismatch was established. These historical rows remain ineligible. No 2-second relaxation is authorized. A whole-second event at an ambiguous or post-window boundary is inadmissible unless the frozen contract proves ordering.
4. Trading date comes from an explicit authoritative venue/calendar identity. `weekday()` is not a holiday calendar. Missing calendar or instrument contract continuity blocks only dependent fields.
5. `INHERITED_VERIFIED` describes lineage; it does not replace the original capture status or independently make a value strategy-ready.

## Graph contracts (schema v1)

- `TradingSessionIdentity`: ISO trading date, venue/calendar ID + version, market segment, instrument/contract identity, schema version. No inferred identity.
- `RunEpoch`: unique run ID, source SHA, config hash, session identity, start/end/heartbeat, process identity. Run IDs never stand in for trading-session IDs.
- `ImmutableEvidenceNode`: content-addressed canonical payload; logical key + node hash; immutable source reference/hash; source/receive/selected/as-of timestamps; status, quality, coverage/gaps, instrument, venue/session and source contract.
- `EvidenceDependencyEdge`: parent and child node IDs/hashes, typed requirement, exact version/time predicate, verifier outcome and blocker reason.
- `DailyHeritageManifest`: immutable run and session identity; same-day and previous-session references; graph root hash; partial/gap labels; schema. Published atomically to a unique manifest file; any convenience pointer is explicitly non-authoritative.
- `RollingPrerequisiteManifest`: exact eligible sessions and raw daily source hashes; calendar and formula version; instrument basis, cutoff/as-of, completeness/null policy, checksum; independently recomputed value.
- `CausalReadiness`: per-strategy required input contract/version, accepted node hashes, typed blockers, evaluation and entry windows separately. Readiness never follows from file presence or CAPTURED alone.

Graph acceptance requires all parents to resolve and verify; no cycles; deterministic topology; unique content identity; conflicting logical-key hashes return `CONFLICT`; temporal availability at decision instant; exact venue/session/instrument/contract closure; no stale derived manifests; no cross-day intraday CAS/candidate/decision/order-state transfer.

## Dependency DAG / implementation sequence

`calendar+instrument+frozen contract -> required session ancestors -> immutable raw evidence -> source verifier -> daily/rolling prerequisite manifest -> same-day run references + current-run events -> heritage graph -> per-strategy readiness -> existing observations/candidates/decisions (unchanged authority chain)`.

The normalized callback emits a process-stream source-event ID and canonical envelope hash; CAS validates that envelope, requires selected exchange epoch to equal the source event epoch, and retains local receive epoch separately without equality coercion. Per-run capture persistence is lock-serialized and atomically merged. The versioned heritage graph, explicit same-session run index, injected-calendar prior-session resolver, strategy-local readiness evaluator, rolling series recomputation and separate verifier are implemented and tested. With explicit user authorization, the read-only observer loads only a pinned verified T1 manifest, passes per-strategy readiness into the shadow registry and records each accepted field hash/blocker with resulting observations/checkpoints, and publishes/loads same-session CAS heritage after drain; the cycle snapshot merges verified current and inherited rows. Additional runtime work records bounded per-token callback coverage with hash validation and conservative downtime from verified prior reports. A persistent CAS evaluation ledger claims source-event-pair identity and stores completed receipts so restart replay is blocked before evaluator invocation. T−1 readiness now binds Opening Drive to exactly one source-closed `FUTURES_BAR`, 1-minute interval, `BAR_END`, complete status, previous eligible date at exactly 15:29:00 IST and matching event epoch/value; prior/current futures contract-key equality is strict. Rolling SMA readiness requires exactly 200 calendar-supplied eligible sessions, exactly 200 ordered source daily closes with canonical per-row content digests, adjustment/formula identity, and independent result/checksum recomputation. The independent verifier repeats these semantic checks rather than trusting the loader report. No entry, order, paper/live, broker, or threshold authority is added.

## Multi-writer, publication, migration

Use unique content-addressed manifest files. Publication is temp-write, flush/fsync, atomic rename, then hash reread. Logical index updates must use process-safe exclusive creation/CAS; same logical key with a different hash is a visible conflict. Readers ignore temp/unsealed files. Idempotent identical publication is accepted. No in-place mutation or symlink authority. Unknown schema versions reject. Legacy records without original source/hash closure are `LEGACY_UNVERIFIED`; no rewrite of raw run evidence.

## Acceptance matrix (design baseline)

V01 same-day reuse only when source closure passes; V02 tamper rejection; V03 wrong date/venue/instrument rejection; V04 competing hashes conflict; V05 source-vs-receive policy explicit; V06 ambiguous whole-second boundary rejects; V07 gap persists; V08 duplicate event idempotency; V09 exact prior-session 15:29 ancestry; V10 authoritative holiday calendar or block; V11 missing 15:29 blocks only Opening Drive; V12 independent SMA recomputation; V13 incomplete 199-bar/missing/roll-ambiguous series blocks; V14 no future ancestor; V15 strategy-local blocking; V16 no expired-window backdating; V17 concurrent/crash publication has no partial head; V18 changed ancestor invalidates derived closure; V19 multi-run/multi-day fixture proves no CAS bleed; V20 absent/partial/legacy source field-specific block; V21 measured coverage gaps propagate; V22 authority snapshots remain read-only and unchanged.

## Scope decision and hard boundaries

Current raw artifacts establish a CAS source/selected binding defect and missing cross-run linkage. The source event envelope now exists for future normalized observations, but it cannot retroactively verify older rows. The repository holiday adapter is not authoritative enough for cross-day use and no sealed exact futures close or 200-session NIFTY50 input series was established. Read-only observer and shadow-readiness wiring is implemented and fixture-tested under explicit user authorization. Real T−1 promotion and fresh-session verification remain blocked pending those external authorities and a separately authorized operator session. Per-token callback counts are fixture-verified; scheduler cadence and downstream per-token correlation remain unknown. The bounded historical diagnostic found 8,971 pulses and 5,916 selected references (51×116) in a stable 2026-09-28 run, with 347.947-second maximum token receipt interval; selected rows lack exchange event time/price, so this is not market coverage evidence. During the audit, existing PID 82150 was confirmed active in the 2026-09-29 run `meg-live-2026-09-29-4533aa1ab52b-f0aa2c226d8e`. It was not signaled or stopped. Unstable files from the earlier inventory/measurement were flagged, and no raw files were read after process discovery. The 2026-09-28 and 2026-09-29 session trees were explicitly inventoried into `/Volumes/TradeBotData/offline_evidence/session_continuity_20260929/legacy_index`; inventory hashes are recorded in `SOURCE_AND_HERITAGE_MANIFEST.json`. These bounded inventories leave source files untouched and every legacy record `LEGACY_UNVERIFIED`. Synthetic tests cannot assert historical data or fresh-session behavior.

### Continuation audit on the user-designated branch

- The user-designated branch was rechecked at `12d01da414d9a1ffc13718390e2c950c9f621bfd`. Its two feed commits were preserved in a dedicated integration worktree; the launch-plan token resolver and configured tick queue capacity were retained during conflict resolution.
- That branch's observer still called the legacy T-1 loader, which merged launch-plan values, arbitrary state-root JSON, and environment overrides; it could also label the current selected futures key as the prior contract key. The runtime now uses the pinned manifest hash, approved-root check, frozen contract hashes, target session and instrument checks, and independent heritage verifier. The legacy helper remains as a compatibility shim but returns only null facts and `PINNED_HERITAGE_MANIFEST_REQUIRED`.
- The untracked worktree input `runtime/preflight/t1_prerequisites_2026-09-29.json` has SHA-256 `4a8cc90a9f303ec0cb581bc16b5bd8e4172353f0aae660c13bf31bb9f3be3dda`; it is recorded as `LEGACY_UNVERIFIED` and is not consumed. Its 15:29 value is null/blocked and it contains no 200-session SMA source series. It cannot establish T-1 readiness.
- The designated worktree has no running process whose command or working directory matches it. The canonical checkout's supervisor, watchdog and scheduler remain present; their ownership relation to external historical session files is unknown. No process was signaled and no protected session file was opened during this continuation.
