# Strategy Truth Phase 3B
## Opening-Range Retest Raw-Publication Boundary

### 1. Repository identity
- Worktree: `/Users/madhuram/tradebot-opening-range-retest-temporal`
- Branch: `audit/opening-range-retest-temporal`
- HEAD: `10f0c0d20e99f3ca84d84578276f43dd2e971a98`
- Accepted ancestry: `PROVEN`

### 2. Evidence-backed repository facts
The repository already proves a durable SQLite pattern for critical state transitions:

- `core/approval_store.py` uses `PRAGMA journal_mode=WAL`, `BEGIN IMMEDIATE`, and `ON CONFLICT(...) DO UPDATE`.
- `core/execution_performance.py` uses SQLite durability, WAL, `BEGIN IMMEDIATE`, and conflict-safe updates.
- `core/feed/runtime_store.py` uses WAL and a busy timeout for atomic snapshot writes.
- No existing opening-range emission-owner module is present in this worktree snapshot.
- `core/candidate_pool_orchestrator.py` is a read-only boundary and is not a durable owner.
- `core/candidate_journal.py`, `core/candidate_lineage_ledger.py`, and `core/candidate_outcome_report_writer.py` are audit/report surfaces only.

### 2.1 Evidence classification

```text
AUDIT EVIDENCE: PROVEN
CURRENT TIME_GATED_SNAPSHOT CLASSIFICATION: PROVEN
ABSENCE OF AN EXISTING COMPATIBLE OWNER: PROVEN
DURABLE_OUTBOX PROTOCOL DESIGN: FROZEN_FOR_IMPLEMENTATION
DURABLE_OUTBOX IMPLEMENTATION: NOT IMPLEMENTED
ATOMIC OUTBOX BEHAVIOR: NOT TESTED
RESTART RECOVERY: NOT TESTED
REPLAY ISOLATION: NOT TESTED
EFFECTIVELY-ONCE RAW PUBLICATION: NOT PROVEN IN RUNTIME
```

### 3. Authoritative raw-publication model
Frozen model:

```text
AUTHORITATIVE RAW PUBLICATION MODEL: DURABLE_OUTBOX_ACCEPTANCE
```

This model freezes the only authoritative raw-candidate publication boundary:

- Candidate proposal is not published.
- A raw candidate becomes authoritative only when the accepted lineage row and the unique outbox row are committed in the same SQLite transaction.
- The accepted raw candidate is the durable outbox acceptance, not the downstream acknowledgement.
- Lineage `EMITTED` means the durable raw-publication intent exists and is authoritative.
- Outbox `PUBLISHED` means downstream delivery has been acknowledged.
- Downstream delivery is a separate concern from raw publication.

### 4. Frozen vocabulary
The protocol uses these terms exactly:

- `candidate proposal`: pre-commit strategy output
- `raw candidate`: durable accepted setup publication intent
- `lineage`: immutable setup identity and state record
- `outbox`: durable delivery queue for already accepted raw candidates
- `PUBLISHED`: downstream acknowledgement, not raw acceptance
- `EMITTED`: durable raw-publication acceptance on the lineage row

The following tentative terms are rejected for the canonical protocol:

- `PENDING_PUBLICATION`
- `PUBLISHING`
- `PUBLICATION_PENDING`
- `PUBLICATION_FAILED` as a durable lineage state
- `DISCOVERED` as a durable owner state

`DISCOVERED` may still exist as trace-only strategy narration, but it is not a durable publication state.

### 4.1 Reporting placeholder semantics

`UNKNOWN_NOT_READ`:
- an evidence/reporting placeholder used when the owner could not establish the current durable state
- persisted: no
- valid lineage state: no
- valid outbox publication state: no
- allowed database value: no
- meaning: the relevant durable row was not successfully read or its current state was not newly proven
- mutation implication: none may be inferred

`UNKNOWN_STORED_STATE`:
- storage was read and contained an unrecognized persisted value
- result: `OWNER_STATE_CONFLICT`
- fail closed

`UNKNOWN_NOT_READ` is never a persisted enum value, schema constraint, or database row value.

### 5. Canonical state layers

#### 5.1 Strategy trace layer
This layer explains what the strategy observed before the durable write:

- `DISCOVERED`
- `VALIDATING`
- `READY_FOR_PUBLICATION`
- `BLOCKED`
- `INVALIDATED`
- `EXPIRED`

These states are not the durable owner. They do not represent publication.

#### 5.2 Durable lineage layer
This layer is the authoritative raw-publication record:

- `EMITTED`
- `INVALIDATED`
- `EXPIRED`

Meaning:

- `EMITTED`: the raw candidate is durably accepted and must not be emitted again for the same `setup_id`
- `INVALIDATED`: the setup failed causality or was structurally revoked before publication
- `EXPIRED`: the setup window elapsed before publication

`setup_id` is retained on `INVALIDATED` and `EXPIRED` lineages for immutable traceability.

#### 5.3 Outbox layer
This layer owns downstream delivery only:

- `PENDING`
- `LEASED`
- `PUBLISHED`
- `RETRYABLE_FAILED`
- `FAILED_FINAL`

Meaning:

- `PENDING`: accepted raw candidate awaits consumer delivery
- `LEASED`: exactly one consumer owns the delivery attempt
- `PUBLISHED`: downstream delivery is acknowledged
- `RETRYABLE_FAILED`: delivery attempt failed but can be retried
- `FAILED_FINAL`: delivery cannot be recovered

The outbox does not redefine raw publication. It only transports an already accepted raw candidate.

### 6. Atomic acceptance boundary
The authoritative boundary is the transaction that commits:

1. the lineage row with state `EMITTED`
2. the unique outbox row with state `PENDING`

Exactly one durable write path exists for an accepted raw candidate.

If the transaction does not commit, the raw candidate was not accepted.

If the transaction commits, the raw candidate is authoritative even if downstream delivery has not yet happened.

### 7. Deterministic per-call outcomes
The protocol must not use conditional `or` outcomes for the same input condition.

#### 7.1 Publication-call outcomes
- `ACCEPTED_FOR_PUBLICATION`
- `ALREADY_EMITTED`
- `LINEAGE_INVALIDATED`
- `LINEAGE_EXPIRED`
- `OWNER_BUSY`
- `OWNER_UNAVAILABLE`
- `OWNER_STATE_CONFLICT`
- `ERROR`

#### 7.2 Outbox-lease outcomes
- `LEASE_GRANTED`
- `LEASE_HELD`
- `ALREADY_PUBLISHED`
- `NOT_DELIVERABLE`
- `OWNER_BUSY`
- `OWNER_UNAVAILABLE`
- `OWNER_STATE_CONFLICT`
- `ERROR`

#### 7.3 Delivery-call outcomes
- `DELIVERED`
- `ALREADY_PUBLISHED`
- `RETRYABLE_FAILED`
- `FAILED_FINAL`
- `OWNER_BUSY`
- `OWNER_UNAVAILABLE`
- `OWNER_STATE_CONFLICT`
- `ERROR`

Each call returns exactly one outcome from its own family. No identical condition has multiple possible outcomes.

### 8. Lease policy
Frozen config key:

```text
OPENING_RANGE_RETEST_PUBLICATION_LEASE_SECONDS
```

Frozen lease rule:

- Missing config: use default `30`
- Valid: integer from `5` through `300` inclusive
- Integer below `5`: configuration error
- Integer above `300`: configuration error
- Zero: configuration error
- Negative: configuration error
- Non-integer: configuration error

Frozen effective lease formula:

```text
lease_expires_at_iso = lease_acquired_at_iso + validated_lease_seconds
```

Both timestamps are stored in UTC ISO-8601 format.

The lease is only for the outbox delivery owner. It does not change the raw publication boundary.

### 9. Schema and index contract
No production schema change is made in this task. This section freezes the expected protocol shape for future implementation.

#### 9.1 Lineage table contract
Frozen lineage columns:

- `setup_id`
- `strategy_id`
- `contract_version`
- `schema_version`
- `source_component`
- `symbol`
- `session_date`
- `direction`
- `boundary_type`
- `normalized_boundary_value`
- `breakout_timestamp_iso`
- `history_hash`
- `candidate_fingerprint`
- `state`
- `created_at_iso`
- `emitted_at_iso`
- `invalidated_at_iso`
- `expired_at_iso`

Frozen causal evidence slice:

- `history_hash` proves the completed-bar evidence used to construct one proposal.
- `history_hash` starts at the 09:15 Asia/Kolkata opening-range bar for the setup session.
- `history_hash` ends at the first qualifying continuation bar, inclusive.
- Included bars: every valid completed one-minute bar from 09:15 through the first qualifying continuation bar.
- Excluded bars: all bars after the first qualifying continuation bar, receipt-time metadata, mutable runtime annotations, owner state, outbox state, and downstream delivery state.
- Canonical bar serialization: `timestamp_iso_ist`, `open`, `high`, `low`, `close`.
- Bars are ordered strictly by timestamp.
- Timestamp is normalized to ISO-8601 with `+05:30`.
- Numeric values are normalized through the frozen Decimal contract.
- Volume is excluded unless volume becomes a mandatory temporal input.
- Dictionary insertion order does not affect the hash.
- Encoding is UTF-8.
- Hash algorithm is `sha256`.
- `history_hash = sha256(canonical serialization of the frozen causal slice)`.
- Future bars do not alter `setup_id`, `history_hash`, `candidate_fingerprint`, `candidate payload semantic fields`, or `proposal_ready_at_iso`.

Frozen proposal boundary:

- `history_hash` and the candidate fingerprint are generated at the same frozen proposal boundary.
- Proposal boundary: first qualifying continuation bar.
- Candidate fingerprint input: existing semantic fingerprint fields only.
- Temporal metadata may be persisted as evidence but does not alter ranking or score.
- Future bars do not alter the accepted proposal payload or fingerprint.

Required uniqueness:

- primary key or unique key on `setup_id`

Required lookup indexes:

- `(session_date, symbol, state)`
- `(symbol, session_date, direction, state)`
- `(strategy_id, session_date, state)`

#### 9.2 Outbox table contract
Frozen outbox columns:

- `outbox_id`
- `setup_id`
- `candidate_payload_json`
- `candidate_fingerprint`
- `publication_state`
- `publication_attempts`
- `created_at_iso`
- `next_attempt_at_iso`
- `published_at_iso`
- `last_attempt_at_iso`
- `last_error`
- `lease_token`
- `lease_owner_id`
- `lease_acquired_at_iso`
- `lease_expires_at_iso`
- `schema_version`

Required uniqueness:

- primary key `outbox_id`
- unique key on `setup_id`

Required lookup indexes:

- `(publication_state, next_attempt_at_iso)`
- `(publication_state, lease_expires_at_iso)`
- `(lease_expires_at_iso)`
- `(setup_id)`

#### 9.3 Allowed persistence primitives
- SQLite
- WAL mode
- `BEGIN IMMEDIATE`
- conflict-safe insert
- or an upsert whose conflict branch performs no updates to immutable lineage fields

#### 9.4 Immutable comparison and overwrite rules
Frozen immutable comparison set:

- `strategy_id`
- `contract_version`
- `schema_version`
- `source_component`
- `symbol`
- `session_date`
- `direction`
- `boundary_type`
- `normalized_boundary_value`
- `breakout_timestamp_iso`
- `history_hash`
- `candidate_fingerprint`

Rules:

- Exact immutable match returns `ALREADY_EMITTED`.
- Exact immutable match performs no mutation and writes no second outbox row.
- Any immutable mismatch returns `OWNER_STATE_CONFLICT`.
- Any immutable mismatch performs no mutation and writes no outbox row.
- Immutable mismatch never overwrites provenance, identity, hashes, state, or timestamps.
- `setup_id` equality alone is insufficient to treat a duplicate as idempotent.

The protocol does not require a new service, database, queue, or event bus.

### 10. Restart and replay policy

#### 10.1 Restart
- Accepted lineage rows remain authoritative after restart.
- `PENDING` outbox rows are claimable immediately when `next_attempt_at_iso` is null or `next_attempt_at_iso <= now`.
- `RETRYABLE_FAILED` outbox rows are claimable only when `next_attempt_at_iso <= now`.
- `LEASED` outbox rows are not claimable while `lease_expires_at_iso > now` and become claimable when `lease_expires_at_iso <= now`.
- `LEASED` outbox rows do not imply raw-publication failure.
- `PUBLISHED` outbox rows are terminal.
- `FAILED_FINAL` rows are terminal.

#### 10.2 Session boundary
- Prior active incomplete setups expire at the prior session boundary.
- A new session creates a fresh active namespace.
- Prior session lineages remain immutable history and remain queryable.
- Prior session outbox rows remain queryable history and do not suppress new-session setups.
- Session reset clears only the active session-scoped suppression scope.
- Old lineage rows are retained.
- Old outbox rows are retained or reconciled according to delivery state.
- Old audit evidence is retained.
- Old setup IDs do not suppress new-session setups.
- Database deletion is not part of session reset.

#### 10.3 Replay isolation
- Replay must use isolated storage.
- Replay must not mutate production rows.
- Replay must not claim a different raw-publication meaning for the same `setup_id`.

### 11. Failure transitions

#### 11.1 Acceptance transaction failure
- No durable lineage row is accepted.
- No durable outbox row is accepted.
- The call returns `ERROR`.

#### 11.2 Duplicate raw publication attempt
- Existing `setup_id` plus exact immutable match already in `EMITTED`
- No new raw candidate is accepted
- The call returns `ALREADY_EMITTED`
- Any immutable mismatch returns `OWNER_STATE_CONFLICT`
- Immutable lineage fields are never overwritten

#### 11.3 Delivery failure after acceptance
- Lineage stays `EMITTED`
- Handled retryable failure: outbox becomes `RETRYABLE_FAILED`, lease is cleared, publication attempts increments by 1, last error is recorded, next attempt is set deterministically, and raw publication remains authoritative.
- Process crash, kill, or hang during delivery: outbox remains `LEASED`, no delivery result is recorded, raw publication remains authoritative, and another consumer may reclaim only after `lease_expires_at_iso`.
- Raw publication is not revoked.

#### 11.4 Terminal delivery failure
- Outbox becomes `FAILED_FINAL`
- Lineage remains `EMITTED`
- The accepted raw candidate stays authoritative

#### 11.5 Delivery attempt counting
- `publication_attempts` counts delivery function invocations that began after a lease was acquired.
- Lease acquisition does not increment `publication_attempts`.
- Delivery function start increments `publication_attempts` once.
- Process crash before delivery function start does not increment `publication_attempts`.
- Process crash after delivery function start keeps the attempt counted.
- Repeated terminal-state API calls do not increment `publication_attempts`.

#### 11.6 Lineage invalidation before acceptance
- No raw candidate is accepted
- No outbox row is written
- The call returns `LINEAGE_INVALIDATED`

#### 11.7 Lineage expiry before acceptance
- No raw candidate is accepted
- No outbox row is written
- The call returns `LINEAGE_EXPIRED`

### 12. Acceptance matrix

| CASE | DURABLE LINEAGE STATE | OUTBOX PUBLICATION STATE | RAW-PUBLICATION RESULT | LEASE RESULT | DELIVERY RESULT | RAW PUBLICATION COUNT | DELIVERY ATTEMPTS | EXPECTED TRACE |
|---|---|---|---|---|---|---|---|---|
| first valid publication | `EMITTED` | `PENDING` | `ACCEPTED_FOR_PUBLICATION` | `NOT_CALLED` | `NOT_ATTEMPTED` | `1` | `0` | atomic lineage and outbox acceptance committed |
| duplicate before delivery | `EMITTED` | `PENDING` | `ALREADY_EMITTED` | `NOT_CALLED` | `NOT_ATTEMPTED` | `1 total` | `UNCHANGED` | existing unique outbox retained |
| duplicate after PUBLISHED | `EMITTED` | `PUBLISHED` | `ALREADY_EMITTED` | `NOT_CALLED` | `NOT_ATTEMPTED` | `1 total` | `UNCHANGED, normally >= 1` | published row retained |
| invalidated before publication | `INVALIDATED` | none | `LINEAGE_INVALIDATED` | `NOT_CALLED` | `NOT_ATTEMPTED` | `0` | `0` | immutable invalidation retained |
| expired before publication | `EXPIRED` | none | `LINEAGE_EXPIRED` | `NOT_CALLED` | `NOT_ATTEMPTED` | `0` | `0` | immutable expiry retained |
| lease granted | `EMITTED` | `LEASED` | `NOT_CALLED` | `LEASE_GRANTED` | `NOT_ATTEMPTED` | `1` | `0` | lease acquired |
| lease held | `EMITTED` | `LEASED` | `NOT_CALLED` | `LEASE_HELD` | `NOT_ATTEMPTED` | `1` | `0` | lease still owned by another process |
| stale lease reclaimed | `EMITTED` | `LEASED` | `NOT_CALLED` | `LEASE_GRANTED` | `NOT_ATTEMPTED` | `UNCHANGED` | `UNCHANGED until a new delivery function invocation begins` | stale_lease_reclaimed=true |
| PUBLISHED lease call | `EMITTED` | `PUBLISHED` | `NOT_CALLED` | `ALREADY_PUBLISHED` | `NOT_ATTEMPTED` | `1 total` | `UNCHANGED, normally >= 1` | lease call rejected after publish |
| FAILED_FINAL lease call | `EMITTED` | `FAILED_FINAL` | `NOT_CALLED` | `NOT_DELIVERABLE` | `NOT_ATTEMPTED` | `1 total` | `UNCHANGED, normally >= 1` | lease call rejected after terminal failure |
| delivery success | `EMITTED` | `PUBLISHED` | `NOT_CALLED` | `NOT_CALLED` | `DELIVERED` | `1` | `1` | downstream acknowledgement recorded |
| already-published delivery call | `EMITTED` | `PUBLISHED` | `NOT_CALLED` | `NOT_CALLED` | `ALREADY_PUBLISHED` | `1 total` | `UNCHANGED, normally >= 1` | delivery call sees terminal publish |
| handled retryable delivery failure | `EMITTED` | `RETRYABLE_FAILED` | `NOT_CALLED` | `NOT_CALLED` | `RETRYABLE_FAILED` | `1` | `1+` | retry scheduled deterministically |
| process crash after lease before delivery start | `EMITTED` | `LEASED` | `NOT_CALLED` | `NOT_CALLED` | `NOT_RECORDED` | `1` | `UNCHANGED` | lease remains stored; delivery function did not begin; attempt count was not incremented; row is reclaimable only after lease expiry |
| process crash after delivery start before result commit | `EMITTED` | `LEASED` | `NOT_CALLED` | `NOT_CALLED` | `NOT_RECORDED` | `1` | `incremented by 1 and retained` | delivery function began; attempt remains counted; no delivery outcome was durably recorded; row is reclaimable only after lease expiry |
| terminal delivery failure | `EMITTED` | `FAILED_FINAL` | `NOT_CALLED` | `NOT_CALLED` | `FAILED_FINAL` | `1` | `1+` | no further delivery attempts |
| FAILED_FINAL delivery call | `EMITTED` | `FAILED_FINAL` | `NOT_CALLED` | `NOT_CALLED` | `FAILED_FINAL` | `1 total` | `UNCHANGED, normally >= 1` | delivery already terminal |
| first publication — database busy | `UNKNOWN_NOT_READ` | `UNKNOWN_NOT_READ` | `OWNER_BUSY` | `NOT_CALLED` | `NOT_ATTEMPTED` | `unchanged / not newly proven` | `not applicable` | no durable state newly proven |
| first publication — database unavailable | `UNKNOWN_NOT_READ` | `UNKNOWN_NOT_READ` | `OWNER_UNAVAILABLE` | `NOT_CALLED` | `NOT_ATTEMPTED` | `not proven` | `not applicable` | fail closed |
| lease call — database busy | `UNKNOWN_NOT_READ` or explicit last-known state | `UNKNOWN_NOT_READ` or explicit last-known state | `NOT_CALLED` | `OWNER_BUSY` | `NOT_ATTEMPTED` | `unchanged / not newly proven` | `not applicable` | last-known state may be reported if previously read |
| lease call — database unavailable | `UNKNOWN_NOT_READ` or explicit last-known state | `UNKNOWN_NOT_READ` or explicit last-known state | `NOT_CALLED` | `OWNER_UNAVAILABLE` | `NOT_ATTEMPTED` | `unchanged / not newly proven` | `not applicable` | last-known state may be reported if previously read |
| delivery call — database busy | `UNKNOWN_NOT_READ` or explicit last-known state | `UNKNOWN_NOT_READ` or explicit last-known state | `NOT_CALLED` | `NOT_CALLED` | `OWNER_BUSY` | `unchanged / not newly proven` | `not applicable` | current durable state not newly proven |
| delivery call — database unavailable | `UNKNOWN_NOT_READ` or explicit last-known state | `UNKNOWN_NOT_READ` or explicit last-known state | `NOT_CALLED` | `NOT_CALLED` | `OWNER_UNAVAILABLE` | `not proven` | `not applicable` | fail closed |
| schema mismatch | `UNKNOWN_NOT_READ` or explicit last-known state | `UNKNOWN_NOT_READ` or explicit last-known state | `OWNER_STATE_CONFLICT` | `NOT_CALLED` | `NOT_ATTEMPTED` | `unchanged / not newly proven` | `not applicable` | fail closed on schema drift |
| unknown stored lineage state | `UNKNOWN_STORED_STATE` | `UNKNOWN_STORED_STATE` | `OWNER_STATE_CONFLICT` | `NOT_CALLED` | `NOT_ATTEMPTED` | `unchanged` | `unchanged` | fail closed on unknown lineage state |
| unknown stored outbox state | `EMITTED` | `UNKNOWN_STORED_STATE` | `OWNER_STATE_CONFLICT` | `NOT_CALLED` | `NOT_ATTEMPTED` | `unchanged` | `unchanged` | fail closed on unknown outbox state |
| immutable owner conflict | `EMITTED` | `PENDING` | `OWNER_STATE_CONFLICT` | `NOT_CALLED` | `NOT_ATTEMPTED` | `unchanged` | `unchanged` | immutable fields mismatch; no mutation |

### 13. Explicit non-claims
This protocol freeze does **not** claim:

- production implementation exists
- production schema has been migrated
- historical edge or profitability
- execution readiness
- broker readiness
- live certification
- downstream consumer implementation details beyond the ownership boundary

### 14. Final frozen statement
The authoritative raw-candidate publication boundary for `opening_range_retest_v1` is the durable SQLite transactional outbox acceptance transaction.

Everything before that boundary is a candidate proposal.
Everything after that boundary is either raw-publication lineage truth or downstream delivery truth.
