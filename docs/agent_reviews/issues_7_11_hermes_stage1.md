# Hermes Stage 1 — Issues 7–11 contracts

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Scope and authority

Offline engineering only. `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`; orders placed/modified/cancelled are zero. Preserve strategy rules and configured token universe. Do not alter feed freshness, risk, or kill-switch gates. The worktree is isolated; the canonical dirty checkout remains untouched.

## Findings and contracts

- Issue 7: captured strategies were fail-closed due absent T-1 evidence. Loader validation is not weakened. Do not synthesize or fetch prerequisite data until canonical source, calendar, as-of, and fields contract are proven.
- Issue 8: captured heritage has no verified prior interval. Do not reconstruct CAS primitives from bars without a source-event identity and frozen causal contract.
- Issue 9: the MEG shadow OHLC buffer is isolated from strategy/execution market data, and repository code has a completed-bar SQLite store. Add persistence only to that shadow path. Every store write must carry an event-time completion cutoff and be rejected unless `bar_start + interval <= completed_as_of`; writes are immutable and concurrent identical retries idempotent. Namespace by session date, retain original live provenance and unknown volume, restore only bars whose interval is complete at restart event-time and whose stored session date equals the active date. Any identity/hash/storage conflict blocks restoration and emits an explicit failure; it cannot silently become empty/healthy. Recovered bars are historical evidence and must not satisfy current feed/subscription liveness checks or create CAS capture authority. Existing C1/C2 contract callers must also supply their observed completion cutoff.
- Issue 10: additive telemetry source-state patch is in progress and must preserve row conversion/fallback ordering.
- Issue 11: the recorded `global_feed_blocked=true` remains an unconditional blocker. Independently, explicit healthy spot-only dependencies must not be vetoed by option-only staleness or zero option subscriptions; required option dependencies remain blocked by their option domain and identity evidence. No edits to shared transport producers or recovery gates.

## Candidate file scope for Issue 9

- `core/market_session_store.py`: preserve nullable volume and migrate the existing schema conservatively.
- `core/market_event_graph_live_ohlc_buffer.py`: explicit session-scoped store configuration, finalized-bar write-through before buffer mutation, completed-only restart hydration after feed identity reset.
- `core/kite_read_only_observation_runtime.py`: instantiate a session-date-scoped store inside the governed session directory and configure only the read-only shadow buffer before callbacks start; storage setup failure stays observable/fail-closed for warm-start.
- focused store/shadow/observer tests.

## GSD Stage 2 gates

Baseline before edits is 49 passing tests across store, shadow buffer, live bridge and candle diagnostics. Required next proofs: null volume round-trip; complete-bar persistence and same-date restore; no current-bar restore; duplicate idempotency; conflicting duplicate rejection; corrupt DB rejection; session boundary isolation; feed identity reset rehydrates only prior completed bars; recovered provenance cannot pass current subscription bridge gate; replay fixtures never persist. Then rerun focused issue10 plus issue9 suite and review the diff independently.

**Hermes verdict:** scoped shadow-buffer persistence is authorized by the Issues 7–11 repair request. Runtime behavior remains read-only. Full task remains incomplete until Issues 7/8/11 have safe proven repairs or technically complete UNKNOWN dispositions, all required tests and broader relevant regressions, and independent verification.

## Cross-issue authority check

`core/market_session_store.py` is source-hash pinned by the candidate feed dependency registry. Any legitimate modification to its persistence contract must update only the recorded digest after the implementation is final, then rerun the registry/symbol-safety tests. This metadata update does not grant execution eligibility: partial declarations, unresolved identities, and authority checks must continue to block.

## Issue 10 re-attack — observer source routing

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**status:** design approved for narrow offline implementation

Repository call-graph inspection confirmed two different decision paths. The read-only observer appends its governed decision rows to `output_root/candidate_decisions.jsonl`, then invokes `produce_and_store_runtime_snapshots`; that producer's fallback is hard-coded to `logs/desks/<DESK_ID>/candidate_decisions.jsonl`. This mismatch explains why observer-run advisory output can report a missing fallback even while the observer's own decision ledger exists. It does not prove that the mismatch caused upstream candidate starvation.

The producer contract will accept an optional caller-owned candidate-decision path. Only the observer supplies its session-scoped ledger; legacy/orchestrator calls retain the configured desk fallback. The reader must ignore an unterminated final JSONL record so a concurrent append cannot promote a partial tail into an accepted advisory row. Completed newline-terminated rows remain eligible and malformed completed rows remain visible through parse/schema notes. No data is mirrored and no second writer is introduced.

**Expected change surface:** observer advisory source selection and JSONL tail acceptance metadata.
**Must-not-change surface:** decision generation, row transformation, ranking, strategy semantics, shared feed health, token universe, broker/order/risk gates, persistent decision storage.
**Observability:** source path plus explicit partial-tail note/state.
**Rollback:** remove the optional argument at the observer call site; default desk fallback remains backward compatible.
**Acceptance proof:** direct source-path test, concurrent-partial-tail simulation followed by completed append, existing fallback tests, observer integration tests, and unchanged authority flags.

## Issue 9 re-attack — persisted timestamp identity

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**status:** design approved for narrow offline implementation

An independent read-only sabotage pass changed only `market_session_bars.ts_epoch` while preserving `ts_ist`, OHLCV, provenance, and the stored row hash. The loader accepted the row and used the tampered epoch for event-time filtering; integrity verification also passed. A backward one-minute shift allowed a 09:15 bar to appear in an as-of read at 09:15:30, before its 09:16 completion boundary. This is a persistence identity defect and can create point-in-time lookahead.

**Invariant:** normalized epoch derived from the stored timezone-aware `ts_ist` must equal the persisted `ts_epoch` within a strict sub-millisecond tolerance before any row can enter the loaded cache or integrity PASS result. A mismatch raises `SessionMemoryConflict` on load and is an explicit integrity failure. The as-of filter must never trust an epoch that disagrees with the timestamp used to hash the bar.

**Expected change surface:** `MarketSessionStore._load` and `MarketSessionStore.verify_integrity`; tests mutate persisted epoch forward and backward while keeping the original row hash.
**Must-not-change surface:** row schema/hash generation, bar aggregation, timeframe derivation, strategy/CAS wiring, session boundaries, risk/order/broker authority.
**Attack acceptance:** forward-shifted epoch must fail startup read and integrity; backward-shifted epoch must not be returned at a pre-completion cutoff and must fail integrity. A valid unmodified row still reopens and derives normally.
**Rollback:** revert the epoch-vs-`ts_ist` comparison and its tests; legacy rows with internally inconsistent timestamp encodings will then remain undetected, so rollback restores the known defect.

## Issue 11 re-attack — observer snapshot consumer contract

Repository call-path inspection found that `produce_and_store_runtime_snapshots` supplies the observer with an envelope containing symbol health under `feed_health_truth_latest.feed_health_truth.symbols`, while `StrategyMarketSnapshotBuilder` reads only top-level `symbols`. The observer's market snapshot carries authoritative spot quote metadata separately. The current consumer can therefore produce no strategy-shadow snapshots from the actual wrapped runtime payload, and a direct unwrapping alone still lacks instrument metadata.

**Authorized repair scope:** update only the read-only shadow snapshot builder to unwrap the known runtime envelope and join health summaries to matching market-snapshot rows by exact normalized symbol. Preserve the existing direct-payload contract. Do not infer option/futures identity from symbol text or create snapshots without explicit instrument evidence. For the observer's exact spot quote row, require exact symbol/token quote metadata and explicit fresh quote/domain evidence before labeling spot health healthy. Any `global_feed_blocked=true`, disconnected websocket, unsafe feed/runtime state, absent required domain, missing quote identity, or non-fresh quote stays `DEGRADED`/blocked. Unrelated option-only degradation may be isolated only when the envelope explicitly declares symbol aggregate scope, explicit `global_feed_blocked=false`, websocket connected, and `INDEX_SPOT` explicitly `HEALTHY` for the joined identity.

**Must-not-change surface:** feed producers, shared transport/recovery behavior, `feed_ok`, candidate authority, strategy rules, ranking, instrument universe, execution/risk/broker behavior.
**Acceptance:** actual wrapper shape plus exact spot market metadata creates one spot shadow snapshot; unrelated option staleness does not degrade that spot-only snapshot under the explicit scope contract; global transport/runtime failure and missing/unknown spot evidence remain degraded or absent; unrelated or unclassified symbols are not invented.
**Rollback:** revert the snapshot consumer join; the live shadow observation regression returns while shared feed and execution behavior remains unchanged.

### Neighbor attack — malformed persisted epoch type

A follow-up verifier probe stored nonnumeric TEXT in `ts_epoch`. Reads failed closed with a raw `ValueError`, while `verify_integrity` also raised instead of returning a structured `FAIL`. The expected contract is uniform corruption handling: a malformed epoch raises `SessionMemoryConflict` from `_load`; the integrity scan appends an `invalid_row` failure and returns `FAIL`. The new negative test preserves all other row fields and verifies both paths. This is an error-reporting and fail-closed contract repair; it does not permit coercing malformed epochs or treating them as absent.
