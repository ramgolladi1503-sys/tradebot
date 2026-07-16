# 1. Repository identity
Worktree: `/Users/madhuram/tradebot-opening-range-retest-temporal`
Branch: `audit/opening-range-retest-temporal`
HEAD: `10f0c0d20e99f3ca84d84578276f43dd2e971a98`
Accepted ancestry: `PROVEN`

# 2. Production call chain
Registry entry: `strategies.strategy_registry.OPENING_RANGE_BREAKOUT`
Production file: `strategies/movement/opening_range_breakout.py`
Production callable: `generate_opening_range_retest_candidates`

Direct production call proof:
- The audit tests import `generate_opening_range_retest_candidates` from `strategies.movement.opening_range_breakout`.
- No copied strategy, fake oracle, test-only wrapper, or mock generator is used.
- The exact callable invoked by the audit tests is the real production function `strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates`.

Current call path:
`strategies.strategy_registry.OPENING_RANGE_BREAKOUT` -> `strategies/movement/opening_range_breakout.py` -> `generate_opening_range_retest_candidates` -> `core.movement_contract.StrategyCandidate`

# 3. Current candidate fingerprint
Observed favorable-snapshot fingerprint:

`opening_range_retest_v1 | BUY_CALL | RAW_CANDIDATE | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`

Rounded harness trace fingerprint:
`opening_range_retest_v1 | BUY_CALL | RAW_CANDIDATE | 0.451504 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`

Directional control fingerprint:
`opening_range_retest_v1 | BUY_PUT | RAW_CANDIDATE | 0.4509528049866429 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`

# 4. Current snapshot dependencies
The current production callable consumes these snapshot fields or snapshot-derived fields:

- `minutes_since_open`
- `spot_ltp`
- `vwap`
- `orb_high`
- `orb_low`
- `option_ce_ltp` / `option_pe_ltp`
- `ce_premium_change` / `pe_premium_change`
- `ce_spread_pct` / `pe_spread_pct`
- `ce_depth` / `pe_depth`
- `option_ltp_age_sec`
- `quote_source`
- `fallback_used`

It does not consume `completed_bar_history`, causal breakout state, causal retest state, or causal continuation state.

# 5. Completed-history non-dependence
The following histories all produced the same direct production result when the consumed snapshot fields were held fixed:

| Case | Emission | Strategy | Direction | Raw score | Entry trigger | Invalidation | Rank reason | Setup identity |
|---|---:|---|---|---:|---|---|---|---|
| absent | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| empty | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| one valid bar | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| multiple valid bars | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| same bars different order | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| different bar values | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| mixed-session history | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| mixed-symbol history | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| duplicate timestamps | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |
| non-1m cadence | 1 | opening_range_retest_v1 | BUY_CALL | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held | absent |

COMPLETED_HISTORY_RESULT: `PASS_BY_NON_DEPENDENCE`
CAUSAL VALUE: `NONE`
STRATEGY ENFORCEMENT: `NOT_ENFORCED_BY_STRATEGY`

# 6. History-collapse false positives
Three materially different histories collapsed to the same production candidate:

- no historical breakout occurred
- breakout occurred without later retest-hold-continuation
- breakout occurred and then structurally failed

All three produced the same semantic fingerprint:
`opening_range_retest_v1 | BUY_CALL | RAW_CANDIDATE | 0.45150442477876107 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`

SNAPSHOT_FALSE_POSITIVE: `PROVEN`

# 7. Future-mutation classification
Decision prefix used in the audit harness: prefix 3.

Future path A:
- later bars collapse inside the opening range

Future path B:
- later bars form an apparent retest and continuation

Future path C:
- later bars break the opposite boundary

Observed result:
- `emission_count = 3` for each path
- `first_emission_checkpoint = 2026-07-14T09:18:00+05:30`
- semantic fingerprints identical across A/B/C
- no setup identity appears in candidate evidence

FUTURE_MUTATION_RESULT: `PASS_BY_NON_DEPENDENCE`
CAUSAL VALUE: `NONE`

# 8. Physical-truncation classification
Full dataset at the decision prefix compared to the physically truncated dataset:

- full trace emission count: `3`
- truncated trace emission count: `1`
- first emission checkpoint: `2026-07-14T09:18:00+05:30`
- `full_trace.steps[:3] == truncated_trace.steps`: `True`

PHYSICAL_TRUNCATION_RESULT: `PASS_BY_NON_DEPENDENCE`
CAUSAL VALUE: `NONE`

# 9. Repeated-emission evidence
Scenario A: identical frozen snapshot evaluated repeatedly
- evaluation count: `5`
- emission count: `5`
- first emission checkpoint: `2026-07-14T09:16:00+05:30`
- semantic fingerprint: identical across all evaluations
- repeated fingerprint count: `4`
- raw score sequence: `[0.451504, 0.451504, 0.451504, 0.451504, 0.451504]`
- setup_id presence: `ABSENT`

Scenario B: evolving snapshot values that remain favourable
- evaluation count: `5`
- emission count: `5`
- first emission checkpoint: `2026-07-14T09:16:00+05:30`
- semantic fingerprint: identical across all evaluations
- repeated fingerprint count: `4`
- raw score sequence: `[0.451504, 0.451504, 0.451504, 0.451504, 0.451504]`
- setup_id presence: `ABSENT`

REPEATED_EMISSION: `PROVEN`
single-emission rule: `NOT IMPLEMENTED`
setup identity: `ABSENT OR NOT ENFORCED`

# 10. Invalidation causality
Observed candidate metadata:
- `invalid_if = price_returns_inside_opening_range`

Observed behavior:
- the string is descriptive metadata only
- invalidation memory is absent
- repeated evaluation after a later inside-range history still emits the same candidate
- no fresh setup distinction is enforced by production
- no revival block exists

INVALIDATION FIELD: `DESCRIPTIVE_METADATA_ONLY`
INVALIDATION MEMORY: `ABSENT`
REVIVAL BLOCK: `NOT IMPLEMENTED`
FRESH SETUP DISTINCTION: `NOT IMPLEMENTED`

# 11. Directional contract
Classification: `BIDIRECTIONAL`

Direct answers:
- Does production currently emit BUY_PUT? `YES`
- Does the strategy name imply bidirectional behavior? `YES` in current implementation and registry wiring
- Would adding BUY_PUT be preservation or a new feature? `PRESERVATION`, because BUY_PUT already exists in production

# 12. Harness capability versus strategy evidence
HARNESS SELF-TEST PASSED:
- `python -m pytest -q tests/test_strategy_temporal_harness.py` passed
- the harness correctly proved its own prefix traversal, truncation, session reset, invalidation, and repeated-emission controls

PRODUCTION STRATEGY PROPERTY PROVEN:
- the audited production strategy is time-gated snapshot logic, not causal opening-range retest logic
- the production callable repeats the same candidate on favorable snapshots
- the production callable ignores completed-bar history

# 13. Frozen temporal repair contract
Implementation-ready minimum:

Evidence-backed frozen semantics:

- use completed 1-minute history or an equivalent approved causal state object as the source of temporal truth
- session semantics are Asia/Kolkata, with the regular session opening at `09:15` and closing at `15:30`
- the opening range is the first `15` completed one-minute candles in session
- the final opening-range candle must be completed before ORB evidence becomes authoritative
- authoritative ORB high/low are derived from the completed opening-range bars by `max(high)` / `min(low)`
- history used for the repair path must remain same-symbol, same-session, strictly ordered, and 1-minute cadence only
- emit only after opening range completion, breakout, later return to the ORB boundary, retest hold, and a strictly later continuation trigger
- preserve the current BUY_CALL / BUY_PUT availability if the causal sequence truly exists
- emit once per setup lineage
- keep the existing raw-score formula unchanged when the causal sequence is present
- emit deterministic `STRATEGY_EVIDENCE_BLOCKED` evidence when the causal sequence is missing, malformed, or incomplete
- keep the existing snapshot-field blocks for missing `minutes_since_open`, `orb_high`, and `orb_low`
- do not change thresholds, ranking, or downstream ownership

What is not yet frozen:
- exact breakout, retest, hold, and continuation rules
- exact setup identity schema
- exact single-emission memory location
- exact expiry bounds

# 14. Unresolved design decisions
DECISION REQUIRED items:

- breakout, retest, hold, and continuation thresholds
- invalidation and expiry thresholds
- setup identity serialization and persistence location
- single-emission memory ownership
- same-bar breakout-and-retest and same-bar retest-and-continuation policy
- whether supplied ORB values are accepted as authoritative or normalized from completed history on repair inputs

# 15. Repair acceptance matrix
| CASE | INPUT HISTORY | SNAPSHOT INPUTS | CURRENT AUDIT RESULT | REPAIR-READY STATUS |
|---|---|---|---|---|
| valid CALL sequence | causal sequence required | favorable snapshot | not proven by current production code | decision required |
| valid PUT sequence | causal sequence required | favorable snapshot | not proven by current production code | decision required |
| opening range incomplete | absent / incomplete history | timing not reached | no candidate required | frozen as fail-closed |
| range complete without breakout | causal history absent | favorable snapshot | no causal setup proven | unresolved |
| breakout without return | causal history absent | favorable snapshot | no causal setup proven | unresolved |
| return without hold | causal history absent | favorable snapshot | no causal setup proven | unresolved |
| hold without continuation | causal history absent | favorable snapshot | no causal setup proven | unresolved |
| continuation before retest | causal history absent | favorable snapshot | no causal setup proven | unresolved |
| same-bar breakout and retest | same bar | favorable snapshot | not proven | decision required |
| same-bar retest and continuation | same bar | favorable snapshot | not proven | decision required |
| wick-only breakout | causal history absent | favorable snapshot | not proven | decision required |
| wick-only retest | causal history absent | favorable snapshot | not proven | decision required |
| market invalidation | causal history absent | favorable snapshot | not proven | decision required |
| metadata-only invalidation regression | causal history absent | favorable snapshot | not proven | decision required |
| invalidated setup cannot revive | causal history absent | favorable snapshot | not proven | decision required |
| fresh setup after invalidation | causal history absent | favorable snapshot | not proven | decision required |
| breakout-to-retest expiry | causal history absent | favorable snapshot | not proven | decision required |
| retest-to-continuation expiry | causal history absent | favorable snapshot | not proven | decision required |
| session reset | new session | favorable snapshot | not proven | decision required |
| single emission | repeated evaluation | favorable snapshot | not proven | decision required |
| repeated evaluation | repeated evaluation | favorable snapshot | not proven | decision required |
| future mutation | later bars differ | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation is snapshot-gated |
| physical truncation | truncated after prefix | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation is snapshot-gated |
| prefix determinism | same prefix sequence | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation is snapshot-gated |
| mixed session | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| mixed symbol | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| unordered timestamps | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| duplicate timestamps | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| non-1m cadence | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| missing OHLC field | malformed history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| insufficient history | short history | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation ignores history |
| fingerprint preservation | favorable snapshot | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation remains unchanged |
| raw-score preservation | favorable snapshot | snapshot fixed | PASS_BY_NON_DEPENDENCE | current implementation remains unchanged |
| unrelated strategy controls | separate strategies | separate controls | PASS | audit harness did not perturb other strategies |

# 16. Unrelated production controls
Opening drive:
- exact callable: `strategies.movement.opening_drive.generate_opening_drive_candidates`
- direct call: `YES`
- mocks used: `NO`
- behavior checked: direct candidate emission from a real snapshot
- result: emitted `opening_drive_v1`

Trend pullback:
- exact callable: `strategies.movement.trend_pullback.generate_trend_pullback_candidates`
- direct call: `YES`
- mocks used: `NO`
- behavior checked: direct candidate emission from a real history-backed context
- result: emitted `trend_pullback_v1`

# 17. Final test results
Focused audit slice:
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py` -> `20 passed`
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py tests/test_strategy_temporal_harness.py tests/test_opening_movement_strategies.py tests/test_trend_pullback_temporal_semantics.py` -> `59 passed`

HARNESS SELF-TEST PASSED: `YES`
PRODUCTION STRATEGY PROPERTY PROVEN: `YES`

# 18. Files changed
Created / modified audit-owned files only:
- `tests/test_opening_range_retest_temporal_audit.py`
- `docs/agent_reviews/strategy_truth_opening_range_retest_temporal_audit.md`

No production files were modified.

# 19. Claim boundary
This evidence closure proves that `opening_range_retest_v1` is currently time-gated snapshot logic with repeated emission under favorable snapshots and no completed-history dependence. It does not prove historical edge, profitability, ranking superiority, execution readiness, live readiness, or production certification.

PRODUCTION LOGIC CHANGED: `NO`
PRODUCTION FILES MODIFIED: `NONE`
TASK-OWNED AUDIT FILES ONLY: `YES`

VERDICT:
OPENING_RANGE_RETEST_REPAIR_DESIGN_READY_WITH_DECISIONS_REQUIRED
