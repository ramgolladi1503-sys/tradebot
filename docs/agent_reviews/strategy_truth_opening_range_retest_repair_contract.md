# 1. Accepted current behavior
`opening_range_retest_v1` is currently `TIME_GATED_SNAPSHOT`, not a causal temporal implementation.

Evidence:
- Production callable: `strategies/movement/opening_range_breakout.py::generate_opening_range_retest_candidates`
- Current gate shape: `strategies/movement/opening_range_breakout.py:37-171`
- It consumes `minutes_since_open`, `spot_ltp`, `vwap`, `orb_high`, `orb_low`, option-side quality fields, and regime score inputs.
- It does not consume `completed_bar_history` or a causal setup state object.
- The audit harness proved the same candidate fingerprint repeats when only favorable snapshot fields remain fixed.

Current implementation classification: `TIME_GATED_SNAPSHOT`
Temporal conformance: `FAILED`
Repair required: `YES`

## 1.1 Evidence classification

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

# 2. Repository-backed frozen base rules
These rules are already supported by repository evidence and are not reopened here.

| Rule | Evidence |
|---|---|
| Session timezone | `core/session_bar_history.py:59-64`, `core/orb_ohlcv_validation.py:33-35` |
| Regular session | `core/session_bar_history.py:59-64`, `core/orb_ohlcv_validation.py:151-176` |
| Opening range is first 15 completed one-minute bars | `core/orb_ohlcv_validation.py:35, 150-167` |
| ORB authoritative only after the 09:29 bar is complete | `core/orb_ohlcv_validation.py:163-167` |
| ORB high / low derivation | `core/orb_ohlcv_validation.py:163-167` |
| Temporal input is completed one-minute bars only | `core/session_bar_history.py:67-75, 188-236` |
| History validity: same symbol, same session, strict ordering, unique timestamps, exact 1m cadence, valid completed OHLC | `core/session_bar_history.py:169-236` |
| Directional contract is bidirectional | `tests/test_opening_movement_strategies.py:100-150`, `tests/test_opening_range_retest_temporal_audit.py:430-458` |

Accepted base contract:
- `SESSION TIMEZONE: Asia/Kolkata`
- `REGULAR SESSION: 09:15–15:30`
- `OPENING RANGE: first 15 completed one-minute bars`
- `OPENING-RANGE BAR WINDOW: 09:15 through 09:29 session bars`
- `ORB AUTHORITATIVE: only after the 09:29 bar is complete`
- `TEMPORAL INPUT: completed one-minute bars only`
- `HISTORY VALIDITY: same symbol, same session, strictly increasing timestamps, unique timestamps, exact one-minute cadence, valid completed OHLC bars`
- `DIRECTIONAL CONTRACT: BIDIRECTIONAL`
- `CURRENT IMPLEMENTATION CLASSIFICATION: TIME_GATED_SNAPSHOT`

# 3. ORB source-of-truth policy
Frozen rule:
- `ORB SOURCE`: recomputed from completed opening-range history.
- `ORB RECONCILIATION`: supplied ORB values are reconciliation inputs only.
- `ORB MISMATCH RESULT`: `STRATEGY_EVIDENCE_BLOCKED`.
- `ORB ABSENCE RESULT`: allowed if the recomputed history is valid.
- `ORB NORMALIZATION`: compare recomputed and supplied values after canonical decimal normalization using the repository numeric contract style: `Decimal(str(value)).quantize(Decimal("0.00000001")).normalize()`.

Concrete examples:
- Example A: recomputed `22150.100000000002`, supplied `22150.10` -> accept after normalization.
- Example B: recomputed `22150.10`, supplied `22150.15` -> block.

Reason:
- The research lane already computes ORB from completed bars in `core/orb_ohlcv_validation.py:150-167`.
- The repair objective is causal truth, not snapshot trust.
- A mismatch should fail closed rather than silently accept conflicting ORB evidence.

Behavioral consequence:
- Repair inputs with recomputed history but conflicting supplied ORB values are blocked.
- Repair inputs with valid completed history and absent supplied ORB values remain eligible once the repaired producer populates them from history.

Status: `FROZEN_RULE`
User approval required: `NO`

# 4. Temporal state machine
Frozen state machine:

| STATE | ENTRY CONDITION | REQUIRED EVIDENCE | ALLOWED NEXT STATES | INVALIDATION | EXPIRY | EMISSION | RECORDED TIMESTAMP |
|---|---|---|---|---|---|---|---|
| `OPENING_RANGE_BUILDING` | session started, fewer than 15 completed bars | completed 1m bars only | `AWAITING_BREAKOUT`, `EVIDENCE_BLOCKED` | malformed history | session end | no | opening-range progress timestamp |
| `AWAITING_BREAKOUT` | ORB complete, no qualifying breakout yet | authoritative ORB high/low, completed bars | `AWAITING_RETEST`, `EVIDENCE_BLOCKED` | malformed history only; staying inside the opening range is not invalidation | none before a confirmed breakout | no | breakout candidate bar timestamp |
| `AWAITING_RETEST` | breakout observed, hold not yet confirmed | breakout bar, later bars | `RETEST_HELD`, `INVALIDATED`, `EXPIRED` | close back inside opening range before hold | retest window expires | no | retest bar timestamp |
| `RETEST_HELD` | retest bar touches the broken boundary and closes on the breakout side | retest bar | `AWAITING_CONTINUATION`, `INVALIDATED`, `EXPIRED` | close back inside opening range | continuation window expires | no | retest bar timestamp |
| `AWAITING_CONTINUATION` | hold confirmed, continuation not yet observed | retest hold evidence | `READY_FOR_PUBLICATION`, `INVALIDATED`, `EXPIRED` | failed continuation / reversal | continuation window expires | no | continuation bar timestamp |
| `READY_FOR_PUBLICATION` | continuation confirmed and candidate proposal constructed | completed causal sequence, deterministic setup_id, candidate fingerprint, candidate payload, temporal provenance | owner acceptance outcome | candidate proposal only; no RAW candidate yet | owner acceptance only | no | proposal_ready_at_iso |
| `INVALIDATED` | post-breakout bar closes back inside opening range before continuation | invalidation trace | fresh breakout only | none | session reset | no | invalidation timestamp |
| `EXPIRED` | setup window elapsed before emission | expiry trace | fresh breakout only | none | session reset | no | expiry timestamp |
| `EVIDENCE_BLOCKED` | malformed history or missing required causal evidence | blocked evidence event | none | none | none | no | blocked-event timestamp |

# 5. Breakout rules
## CALL breakout
Recommended rule:
- The first completed post-range bar whose close is strictly greater than `orb_high`.
- Wick-only breakouts do not count.
- Equality does not count.
- The final opening-range bar cannot be the breakout bar.
- The first completed bar after ORB completion may be the breakout bar.

## PUT breakout
Recommended mirrored rule:
- The first completed post-range bar whose close is strictly less than `orb_low`.
- Wick-only breakouts do not count.
- Equality does not count.
- The final opening-range bar cannot be the breakout bar.
- The first completed bar after ORB completion may be the breakout bar.

## Behavioral consequence
- A wicky probe that fails to close beyond the boundary does not establish a breakout.
- The breakout timestamp is the completed breakout bar timestamp.

User approval required: `NO`

# 6. Retest and hold rules
## CALL retest
Frozen rule:
- A later completed bar reaches `orb_high` from above, with `low <= orb_high` and `close >= orb_high`.
- The bar must remain strictly above the opposite ORB boundary: `low > orb_low`.

## PUT retest
Frozen rule:
- A later completed bar reaches `orb_low` from below, with `high >= orb_low` and `close <= orb_low`.
- The bar must remain strictly below the opposite ORB boundary: `high < orb_high`.

## Retest tolerance
- Use the ORB boundary itself as the tolerance.
- Do not add a new numeric tolerance unless an existing repository convention explicitly requires it.

## Hold confirmation
Frozen rule:
- The retest bar itself confirms the hold when it touches intrabar and closes on the breakout side.
- No additional hold bar is required.

## Same-bar policy for retest/hold
- Breakout and retest on the same bar: `NO`
- Retest and continuation on the same bar: `NO`

## Behavioral consequence
- The retest bar is causal evidence only if it is strictly later than breakout and closes back on the breakout side.

User approval required: `NO`

# 7. Continuation rules
## CALL continuation
Recommended rule:
- A later completed bar closes strictly above the retest-bar high.

## PUT continuation
Recommended rule:
- A later completed bar closes strictly below the retest-bar low.

## Preserved gates
- Existing final option-quality gates remain unchanged after the causal sequence is proven.
- Temporal metadata must not be used to inflate score.

## Behavioral consequence
- Continuation is a later causal confirmation, not the breakout itself.
- Wick-only continuation does not count.
- Equality does not count.

User approval required: `NO`

# 8. Same-bar transition policy
Frozen rule:
- Opening-range completion and breakout on the same bar: `NO`
- Breakout and retest on the same bar: `NO`
- Retest/hold and continuation on the same bar: `NO`

Reason:
- Every causal phase is defined on a strictly later completed one-minute bar.

Alternative rule:
- Allow same-bar transitions only if explicitly documented and causally proven by a future repository change.

Behavioral consequence:
- The strategy remains fail-closed against compressed intrabar sequences.

User approval required: `NO`

# 9. Market invalidation
## CALL invalidation
Frozen rule:
- A completed post-breakout bar closes strictly below `orb_high` before continuation emission.

## PUT invalidation
Frozen rule:
- A completed post-breakout bar closes strictly above `orb_low` before continuation emission.

## Equality
- `close == orb_high` does not invalidate CALL.
- `close == orb_low` does not invalidate PUT.

## Existing metadata interpretation
- `price_returns_inside_opening_range` should mean a completed close back inside the range, not a wick touch.

## Revival rule
- An invalidated setup cannot revive.
- A fresh breakout strictly after invalidation creates a fresh setup identity.

User approval required: `NO`

# 10. Malformed history versus valid incomplete setup
Frozen distinction:

- Missing or malformed required temporal history: `STRATEGY_EVIDENCE_BLOCKED`
- Valid history, opening range incomplete: no candidate
- Valid history, no breakout: no candidate
- Valid history, breakout without retest: no candidate
- Valid history, retest held without continuation: no candidate
- Valid history, setup invalidated: no candidate plus deterministic invalidation trace
- Valid history, setup expired: no candidate plus deterministic expiry trace

Reason:
- Absence of a setup is not a data-quality failure.
- Malformed history is a data-quality failure and must fail closed.

User approval required: `NO`

# 11. Setup identity
## Frozen schema
- `strategy_id`
- `symbol`
- `session_date`
- `direction`
- `boundary_type`
- `normalized_boundary_value`
- `breakout_timestamp`

## Frozen canonical serialization
`opening_range_retest_v1|<symbol>|<YYYY-MM-DD session date>|BUY_CALL or BUY_PUT|ORB_HIGH or ORB_LOW|<normalized boundary>|<ISO-8601 breakout timestamp with +05:30 offset>`

## Frozen hash
- `sha256(canonical_serialization)`

## History hash
- Purpose: prove the causal completed-bar evidence used to construct one proposal.
- Start: the 09:15 Asia/Kolkata opening-range bar for the setup session.
- End: the first qualifying continuation bar, inclusive.
- Included: every valid completed one-minute bar from 09:15 through the first qualifying continuation bar.
- Excluded: all bars after the first qualifying continuation bar, receipt-time metadata, mutable runtime annotations, owner state, outbox state, and downstream delivery state.
- Canonical serialization fields: `timestamp_iso_ist`, `open`, `high`, `low`, `close`.
- Bars are ordered strictly by timestamp.
- Timestamp is normalized to ISO-8601 with `+05:30`.
- Numeric values are normalized through the frozen Decimal contract.
- Volume is excluded unless volume becomes a mandatory temporal input.
- Dictionary insertion order does not affect the hash.
- Encoding is UTF-8.
- Hash algorithm is `sha256`.
- `history_hash = sha256(canonical serialization of the frozen causal slice)`.
- Repeated evaluation after additional future bars reconstructs the same causal slice and therefore the same `history_hash`.
- Future bars must not alter `setup_id`, `history_hash`, `candidate_fingerprint`, `candidate payload semantic fields`, or `proposal_ready_at_iso`.

## Proposal boundary
- Proposal boundary: first qualifying continuation bar.
- Candidate fingerprint input: existing semantic fingerprint fields only.
- Temporal metadata may be persisted as evidence but must not alter ranking or score.
- Future bars must not alter the accepted proposal payload or fingerprint.

## Evidence alignment
- `trend_pullback_v1` already uses deterministic `setup_identity` with contract version, symbol, session date, direction, and timestamps in `strategies/movement/trend_pullback.py:339-433`.
- The opening-range repair should mirror that pattern rather than inventing object identity or counters.

## Behavioral consequence
- Same setup lineage deduplicates cleanly.
- Fresh breakout after invalidation gets a new setup_id.

Status: `FROZEN_RULE`
User approval required: `NO`

## Lineage provenance
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

# 12. State ownership and single emission
## Ownership status
- Primary temporal truth: pure deterministic recomputation from bounded completed history.
- Candidate pool dedupe and candidate normalization are not primary setup owners.
- Temporal strategy result: `READY_FOR_PUBLICATION`
- Canonical raw-publication boundary: `DURABLE_OUTBOX_ACCEPTANCE`
- Canonical ownership model: SQLite-backed transactional outbox keyed by `setup_id`
- Canonical durable lineage state: `EMITTED`
- Canonical downstream delivery state: `PUBLISHED`
- OWNER CALL: `accept_candidate_proposal(...)`
- OWNER RESULT: `ACCEPTED_FOR_PUBLICATION`
- DURABLE EFFECT: lineage state = `EMITTED`; outbox publication_state = `PENDING`; RAW publication count = `1`
- Duplicates with exact immutable match: `ALREADY_EMITTED`; no mutation; no second outbox row; no second RAW candidate
- Duplicate immutable mismatch: `OWNER_STATE_CONFLICT`; no mutation; overwrite forbidden
- Rejected tentative lifecycle: `DISCOVERED -> PENDING_PUBLICATION -> PUBLISHING -> EMITTED`
- Rejected tentative terminal states: `PUBLICATION_PENDING`, `PUBLISHING`, and `PUBLICATION_FAILED` as raw-publication states
- Immutable owner comparison is frozen separately from the temporal proposal state.

## Required trace fields
- `setup_id`
- `setup_state`
- `already_emitted`
- `emission_suppression_reason`

## Behavioral consequence
- One RAW candidate per `setup_id` is the authoritative contract.
- `READY_FOR_PUBLICATION` is only a temporal proposal state.
- Repeated evaluation of the same emitted setup emits nothing once the durable outbox acceptance boundary has been crossed.
- A fresh `setup_id` may emit.
- Session reset clears only the active session-scoped suppression scope.
- Old lineage rows are retained.
- Old outbox rows are retained or reconciled according to delivery state.
- Old audit evidence is retained.
- Old setup IDs do not suppress new-session setups.
- Database deletion is not part of session reset.

Status: `FROZEN_RULE`
User approval required: `NO`

# 13. Expiry
Frozen contract value:
- breakout-to-retest expiry = `5` completed bars
- retest-to-continuation expiry = `3` completed bars

Rationale:
- The 5/3 split is the tighter fail-closed default and is the proposed canonical contract value.
- It reduces stale-setup revival without claiming profitability.
- It is compatible with the existing 15-minute opening-range stage and does not require new temporal machinery.

Behavioral consequence:
- Origin bar age: `0`.
- Breakout-to-retest window: `5` later completed bars.
- Retest-to-continuation window: `3` later completed bars.
- Age 0 is the breakout bar or retest bar that starts the window.
- Age 1 is the first later completed bar.
- Age 5 is the maximum eligible retest bar.
- Age 3 is the maximum eligible continuation bar.
- For each completed bar, evaluate invalidation and qualifying transition first.
- If no transition occurs, evaluate whether the inclusive maximum age has been exhausted.
- Expire only after the maximum-age bar fails to transition.
- The maximum-age bar itself remains eligible for transition.
- Age 6 after the breakout window and age 4 after the continuation window are already expired.
- Same-bar breakout/retest and same-bar retest/continuation remain forbidden.

Status: `FROZEN_RULE`
User approval required: `NO`

# 14. Session reset
Recommended frozen rule:
- Prior active incomplete setups expire at the prior session boundary.
- A new Asia/Kolkata session creates a fresh active namespace.
- Prior invalidated and emitted lineages remain durable history and do not carry active suppression into the new session.
- Prior emitted setup identities do not suppress new-session setups.
- Opening range is recomputed from the new session's first 15 completed bars.

Reason:
- This matches the causal session contract in `core/session_bar_history.py`, preserves immutable history, and prevents carry-over leakage.

User approval required: `NO`

# 15. Scoring and fingerprint preservation
Current scores observed in the frozen fixture:
- CALL raw score: `0.45150442477876107`
- PUT raw score: `0.4509528049866429`

Required repair rule:
- Temporal sequence is an eligibility gate only.
- Existing score formula remains unchanged when the causal sequence is present.
- Existing score inputs remain unchanged.
- Temporal metadata must not affect score or ranking.
- Downstream ownership remains unchanged.

Status:
- Post-repair score preservation is required but not yet proven.

User approval required: `NO`

# 16. Temporal metadata
Proposed metadata contract:

- `temporal_contract`: `opening_range_retest_temporal_v1`
- `temporal_state`: enum
- `opening_range_start_ts`: Asia/Kolkata timestamp
- `opening_range_complete_ts`: Asia/Kolkata timestamp
- `orb_high`: numeric
- `orb_low`: numeric
- `breakout_ts`: Asia/Kolkata timestamp
- `retest_ts`: Asia/Kolkata timestamp
- `hold_ts`: Asia/Kolkata timestamp
- `continuation_ts`: Asia/Kolkata timestamp
- `setup_id`: deterministic string
- `setup_direction`: `BUY_CALL` or `BUY_PUT`
- `setup_age_bars`: integer
- `emission_state`: `NOT_EMITTED | EMITTED | SUPPRESSED_ALREADY_EMITTED`
- `invalidation_ts`: optional Asia/Kolkata timestamp
- `invalidation_reason`: optional deterministic enum
- `expiry_reason`: optional deterministic enum

Classification:
- Candidate evidence: `setup_id`, `setup_direction`, `emission_state`
- Strategy trace only: timestamps, age, invalidation, expiry
- Semantic fingerprint fields: `strategy_id`, direction, raw score, entry trigger, invalid_if, rank_reason
- Non-ranking metadata: all temporal timestamps and trace flags

Compatibility note:
- The metadata contract is sufficient to describe a causal setup lineage, but it does not itself solve the missing emitted-setup owner.
- That ownership gap is the remaining blocker for a fully frozen implementation contract.

User approval required: `NO`

# 17. Decision table
| DECISION | REPOSITORY EVIDENCE | FROZEN / PROPOSED RULE | ALTERNATIVE | BEHAVIORAL CONSEQUENCE | USER APPROVAL REQUIRED |
|---|---|---|---|---|---|
| ORB source-of-truth | `core/orb_ohlcv_validation.py:150-167`, `core/orders/order_intent.py:12-28` | recompute from completed history; normalize supplied values before comparing | trust supplied ORB | fail-closed on mismatch | NO |
| ORB mismatch behavior | research lane computes ORB from history | block mismatch after normalization | accept supplied values | prevents silent ORB drift | NO |
| CALL breakout | current strategy compares snapshot against ORB at `strategies/movement/opening_range_breakout.py:93-98` | first completed post-range close > `orb_high` | wick/high-based breakout | causal breakout only | NO |
| PUT breakout | mirrored current snapshot logic at `strategies/movement/opening_range_breakout.py:110-114` | first completed post-range close < `orb_low` | wick/low-based breakout | causal breakout only | NO |
| Retest touch rule | boundary-touch semantics already exist in current audit evidence | boundary touch allowed | require extra distance | keeps no-new-threshold contract | NO |
| Retest penetration rule | current strategy uses `pct_distance` threshold, but repair stays boundary-based | close on breakout side, intrabar touch allowed, opposite boundary must remain unbreached | deeper penetration threshold | minimizes invented numbers | NO |
| Hold confirmation | current code treats the retest snapshot as the candidate gate | retest bar itself confirms hold | extra hold bar | simpler causal chain | NO |
| Continuation trigger | trend-pullback uses later-bar continuation semantics in `strategies/movement/trend_pullback.py:339-433` | later close beyond retest-bar extreme | breakout-extreme-only | clean post-retest confirmation | NO |
| Same-bar transitions | no repository-backed support found | no same-bar transitions | allow same-bar exceptions | preserves causal sequence | NO |
| Market invalidation | `price_returns_inside_opening_range` metadata already exists in `strategies/movement/opening_range_breakout.py:161-163` | completed close back inside range | wick-only invalidation | fail-closed invalidation | NO |
| Setup identity | trend_pullback uses deterministic setup_identity in `strategies/movement/trend_pullback.py:339-433` | deterministic hash over canonical fields | object identity/counters | stable lineage | NO |
| State ownership | temporal harness uses causal prefix replay in `core/strategy_temporal_harness.py:216-240` | pure recomputation plus a durable SQLite transactional outbox owner keyed by `setup_id` | shared state manager | minimal deterministic ownership | NO |
| Single-emission memory | no opening-range proof exists yet; trend_pullback proves one emitted setup per identity pattern | durable outbox acceptance keyed by `setup_id` | downstream dedup only | repeated eval suppressed after acceptance | NO |
| Breakout-to-retest expiry | no exact repo-backed count found | 5 later completed bars, inclusive | 10 bars | stale setups expire after age-5 evaluation | NO |
| Retest-to-continuation expiry | no exact repo-backed count found | 3 later completed bars, inclusive | 5 bars | stale setups expire after age-3 evaluation | NO |
| Session reset | session-bound history and provenance are explicit in `core/session_bar_history.py:135-155` | prior active incomplete setups expire at the prior session boundary; the new session opens a fresh active namespace based on available completed history | active suppression scope resets; durable lineage, outbox, and audit history remain retained | old records remain queryable; old setup IDs do not suppress new-session setups | NO |

# 18. Repair acceptance matrix
| CASE | COMPLETED HISTORY | EXPECTED STATE TRACE | EXPECTED EMISSION | EXPECTED BLOCK OR INVALIDATION | EXPECTED SETUP ID | EXPECTED FINGERPRINT | EXPECTED SCORE |
|---|---|---|---|---|---|---|---|
| valid CALL | causal sequence present | ORB_BUILDING -> AWAITING_BREAKOUT -> AWAITING_RETEST -> RETEST_HELD -> AWAITING_CONTINUATION -> READY_FOR_PUBLICATION | candidate proposal only | none | deterministic | preserved | preserved |
| valid PUT | causal sequence present | mirrored PUT trace ending at READY_FOR_PUBLICATION | candidate proposal only | none | deterministic | preserved | preserved |
| opening range incomplete | < 15 completed bars | OPENING_RANGE_BUILDING | no candidate | incomplete, not blocked | none | none | none |
| malformed opening range | bad session/order/cadence/OHLC | EVIDENCE_BLOCKED | no candidate | STRATEGY_EVIDENCE_BLOCKED | none | none | none |
| range complete without breakout | ORB valid, no breakout | AWAITING_BREAKOUT | no candidate | no setup yet | none | none | none |
| wick-only CALL breakout | close not beyond `orb_high` | AWAITING_BREAKOUT | no candidate | not a breakout | none | none | none |
| wick-only PUT breakout | close not beyond `orb_low` | AWAITING_BREAKOUT | no candidate | not a breakout | none | none | none |
| close-confirmed CALL breakout | close > `orb_high` | AWAITING_RETEST | no candidate | none | deterministic | preserved | preserved |
| close-confirmed PUT breakout | close < `orb_low` | AWAITING_RETEST | no candidate | none | deterministic | preserved | preserved |
| breakout without retest | no later boundary retest | AWAITING_RETEST | no candidate | pending | deterministic | none | none |
| retest succeeds on maximum eligible age 5 | breakout at age 0; valid retest on later completed bar age 5 | AWAITING_RETEST -> RETEST_HELD -> AWAITING_CONTINUATION | no candidate | none; maximum-age bar remains eligible | retained | none | none |
| retest fails on maximum eligible age 5 | breakout at age 0; no valid retest through age 5 | AWAITING_RETEST -> EXPIRED after age-5 evaluation | no candidate | expiry after evaluating age 5 | retained | none | none |
| age 6 after breakout-to-retest expiry | breakout at age 0; no valid retest through age 5 | EXPIRED | no candidate | already expired; no revival | retained | none | none |
| valid CALL retest | later touch from above and low remains above `orb_low` | RETEST_HELD | no candidate | none | deterministic | preserved | preserved |
| valid PUT retest | later touch from below and high remains below `orb_high` | RETEST_HELD | no candidate | none | deterministic | preserved | preserved |
| retest close inside range | closes back inside ORB | INVALIDATED | no candidate | invalidation | deterministic | none | none |
| hold without continuation | retest held, no later continuation | AWAITING_CONTINUATION | no candidate | pending | deterministic | none | none |
| continuation before retest | continuation-like move before retest | AWAITING_BREAKOUT/AWAITING_RETEST | no candidate | no causal setup | none | none | none |
| continuation succeeds on maximum eligible age 3 | retest at age 0; valid continuation on later completed bar age 3 | AWAITING_CONTINUATION -> READY_FOR_PUBLICATION | candidate proposal only | none; maximum-age bar remains eligible | retained deterministic ID | preserved | preserved |
| continuation fails on maximum eligible age 3 | retest at age 0; no valid continuation through age 3 | AWAITING_CONTINUATION -> EXPIRED after age-3 evaluation | no candidate | expiry after evaluating age 3 | retained | none | none |
| age 4 after retest-to-continuation expiry | retest at age 0; no valid continuation through age 3 | EXPIRED | no candidate | already expired; no revival | retained | none | none |
| same-bar breakout and retest | same completed bar | no candidate | no candidate | blocked by policy | none | none | none |
| same-bar retest and continuation | same completed bar | no candidate | no candidate | blocked by policy | none | none | none |
| valid CALL continuation | later close > retest-bar high | READY_FOR_PUBLICATION | candidate proposal only | none | deterministic | preserved | preserved |
| valid PUT continuation | later close < retest-bar low | READY_FOR_PUBLICATION | candidate proposal only | none | deterministic | preserved | preserved |
| market invalidation | close back inside opening range before continuation | INVALIDATED | no candidate | invalidation trace | retained setup_id | none | none |
| invalidated setup cannot revive | post-invalidation later bars | INVALIDATED | no candidate | revival blocked | retained setup_id | none | none |
| fresh breakout after invalidation | new breakout after invalidation | new setup trace | possible new candidate | fresh lineage | new deterministic id | preserved | preserved |
| breakout-to-retest expiry | no retest within expiry window | EXPIRED | no candidate | expiry trace | retained setup_id | none | none |
| retest-to-continuation expiry | no continuation within expiry window | EXPIRED | no candidate | expiry trace | retained setup_id | none | none |
| single emission | repeated eval of same setup | EMITTED then SUPPRESSED_ALREADY_EMITTED | first only | repeated eval suppressed | same id | preserved | preserved |
| repeat evaluation after emission | same setup_id | SUPPRESSED_ALREADY_EMITTED | no new candidate | already emitted | same id | preserved | preserved |
| fresh setup identity | later legitimate breakout | new setup trace | possible new candidate | fresh lineage | new id | preserved | preserved |
| session ends before retest | confirmed breakout exists; session closes before valid retest | AWAITING_RETEST -> EXPIRED | no candidate | session-end expiry | retained | none | none |
| session ends before continuation | valid retest exists; session closes before valid continuation | AWAITING_CONTINUATION -> EXPIRED | no candidate | session-end expiry | retained | none | none |
| session ends without breakout | valid ORB; no qualifying breakout during session | AWAITING_BREAKOUT -> session closed with no setup | no candidate | none; no setup_id; no durable EXPIRED lineage | none | none | none |
| new session after prior expiry | new-session completed history | OPENING_RANGE_BUILDING or AWAITING_BREAKOUT | no carryover emission | prior expiry retained; active namespace reset | new IDs only after a new breakout | preserved | preserved |
| READY_FOR_PUBLICATION at session boundary | causal sequence completed before session close | READY_FOR_PUBLICATION | proposal must use normal owner acceptance path; no RAW candidate unless owner transaction commits | proposal must not be silently discarded or converted to EXPIRED merely because session reset began | retained | preserved | preserved |
| session reset | prior session ended; new-session completed one-minute history available | prior active incomplete setups expired at prior session boundary; new session opens OPENING_RANGE_BUILDING or AWAITING_BREAKOUT based on valid completed history | no carryover emission | none; active suppression resets; durable lineage, outbox, and audit history remain retained | new session-scoped setup IDs | preserved | preserved |
| future mutation | later bars changed after prefix | prefix trace unchanged | unchanged | none | unchanged | preserved | preserved |
| physical truncation | data truncated at prefix | prefix trace unchanged | unchanged | none | unchanged | preserved | preserved |
| prefix determinism | same prefix replay | same trace | unchanged | none | unchanged | preserved | preserved |
| mixed session | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| mixed symbol | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| unordered timestamps | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| duplicate timestamps | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| non-1m cadence | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| missing OHLC | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| non-finite OHLC | malformed history | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| insufficient history | short history | OPENING_RANGE_BUILDING | no candidate | incomplete | none | none | none |
| ORB supplied/recomputed match | valid history and matching ORB after normalization | normal causal trace | eligible | none | deterministic | preserved | preserved |
| ORB supplied/recomputed mismatch | valid history, mismatched ORB after normalization | EVIDENCE_BLOCKED | no candidate | blocked | none | none | none |
| CALL fingerprint preservation | frozen CALL fixture | unchanged candidate fingerprint | one CALL candidate | none | unchanged | preserved | preserved |
| PUT fingerprint preservation | frozen PUT fixture | unchanged candidate fingerprint | one PUT candidate | none | unchanged | preserved | preserved |
| CALL score preservation | frozen CALL fixture | unchanged candidate fingerprint | same score | none | unchanged | preserved | preserved |
| PUT score preservation | frozen PUT fixture | unchanged candidate fingerprint | same score | none | unchanged | preserved | preserved |
| opening_drive_v1 control | unrelated strategy | unaffected | unchanged | none | n/a | preserved | preserved |
| trend_pullback_v1 control | unrelated strategy | unaffected | unchanged | none | n/a | preserved | preserved |

# 19. Test results
Latest document revision regression: `PASS`

Temporal slice:
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py tests/test_strategy_temporal_harness.py tests/test_opening_movement_strategies.py tests/test_trend_pullback_temporal_semantics.py` -> `59 passed`

SQLite/runtime slice:
- `python -m pytest -q tests/test_approval_binding.py tests/test_order_intent_idempotency.py tests/test_tick_store.py tests/test_feed_debug_runtime_store.py tests/core/test_runtime_snapshot_store.py tests/core/test_market_snapshot_store.py` -> `21 passed`

Previously observed results:
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py` -> `20 passed`
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py tests/test_strategy_temporal_harness.py tests/test_opening_movement_strategies.py tests/test_trend_pullback_temporal_semantics.py` -> `59 passed`

PROPOSED OWNER IMPLEMENTATION: `NOT TESTED`
EFFECTIVELY-ONCE RUNTIME GUARANTEE: `NOT PROVEN`

No production logic was modified for these checks.

# 20. Schema vocabulary
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

# 21. Files changed
Task-owned documentation only:
- `docs/agent_reviews/strategy_truth_opening_range_retest_repair_contract.md`
- `docs/agent_reviews/strategy_truth_opening_range_retest_state_owner_architecture.md`

Existing audit evidence remains preserved in:
- `docs/agent_reviews/strategy_truth_opening_range_retest_temporal_audit.md`
- `tests/test_opening_range_retest_temporal_audit.py`

# 22. Claim boundary
This document freezes the repair contract for `opening_range_retest_v1`. It now aligns the causal rules with the durable outbox acceptance boundary defined in `strategy_truth_opening_range_retest_state_owner_architecture.md`. It does **not** claim historical edge, profitability, execution readiness, or production certification, and it does not modify production code.

Overall contract verdict: `OPENING_RANGE_RETEST_PROTOCOL_FROZEN_ON_DURABLE_OUTBOX_ACCEPTANCE`
