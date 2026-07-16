# Strategy Truth: `opening_range_retest_v1` temporal repair

## Implementation direction
`RIGHT_WITH_GAPS`

## Approved objective
Convert `opening_range_retest_v1` from a snapshot-gated candidate generator into a causal completed-bar implementation using the existing completed-bar history contract, without changing strategy thresholds or downstream ownership.

## What was implemented
- `strategies/movement/opening_range_breakout.py` now requires `completed_bar_history` for the strategy to emit.
- The opening range is recomputed from the first 15 completed one-minute bars in `Asia/Kolkata`.
- Supplied ORB values are treated as reconciliation inputs only; mismatches fail closed with deterministic blocked evidence.
- The strategy scans completed bars causally for breakout, retest, and continuation and emits only when the continuation bar is strictly later than the retest.
- Missing, short, or malformed history now fails closed with `STRATEGY_EVIDENCE_BLOCKED`; there is no snapshot fallback path.
- The emitted candidate keeps the movement-layer `StrategyCandidate.status == RAW_CANDIDATE`, while the temporal proposal state is carried in lineage as `READY_FOR_PUBLICATION`.
- Proposal evidence carries `setup_identity` with `contract_version`, `setup_id`, `history_hash`, and `proposal_ready_at_iso`.
- The accepted causal CALL control remains stable at `0.45150442477876107`.

## Architecture change
`NECESSARY_MINIMAL`

## Starting head
`fe7add395cb1b64556d28e8054da8724c868a031`

## Final head
`pending commit`

## Files changed
- `strategies/movement/opening_range_breakout.py`
- `tests/test_opening_movement_strategies.py`
- `tests/test_opening_range_retest_temporal_audit.py`
- `tests/test_opening_range_retest_temporal_fixture_contract.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_trend_pullback_temporal_semantics.py`

## Production behavior
### Current call chain
`strategies.strategy_registry.OPENING_RANGE_BREAKOUT` -> `strategies/movement/opening_range_breakout.py` -> `generate_opening_range_retest_candidates`

### Causal contract
- Opening range is the first 15 completed one-minute bars in `Asia/Kolkata`.
- Breakout must close beyond ORB high for CALL or below ORB low for PUT.
- Retest must occur strictly later than breakout.
- Continuation must occur strictly later than retest.
- Same-bar breakout/retest and same-bar retest/continuation are rejected.
- Invalid histories and ORB mismatches fail closed.
- Missing completed history, short completed history, and malformed completed history fail closed.
- Later prefixes do not re-emit the same setup lineage.

### Blocked evidence examples
- Missing completed history emits `event=STRATEGY_EVIDENCE_BLOCKED ... reason=missing_required_temporal_evidence`.
- ORB mismatch emits `event=STRATEGY_EVIDENCE_BLOCKED ... reason=invalid_orb_reconciliation`.

## Candidate fingerprints
### Canonical causal CALL control
- `opening_range_retest_v1`
- `BUY_CALL`
- `RAW_CANDIDATE`
- `0.45150442477876107`
- `opening_range_breakout_retest_hold`
- `price_returns_inside_opening_range`
- `opening range breakout retest held`
- temporal proposal state: `READY_FOR_PUBLICATION`

### Control explanation
- The `0.421504` control in `tests/test_opening_movement_strategies.py` is not a different temporal path.
- It is the same causal opening-range sequence scored under a lower `VOLATILITY_EXPANSION` regime input of `0.30` instead of `0.45`.

## Behavior preserved
- Strategy ID and movement type remain unchanged.
- CALL and PUT directional support remain unchanged.
- Pattern scoring formula remains unchanged.
- No broker, order, execution, feed, or profile wiring changed.
- `NO_TRADE_CHOP` and other unrelated strategies were not modified.

## Behavior changed
- Snapshot-only evaluation and short-history fallback were removed.
- Temporal proposal ownership is now explicit in lineage via `READY_FOR_PUBLICATION`.
- Missing or malformed temporal evidence now fails closed instead of producing a fallback candidate.
- The causal path now carries deterministic setup identity and history hash evidence.

## Risk assessment
- This is still a narrow temporal repair. It does not claim profitability or production readiness.
- Remaining risk is limited to future fixture drift if new temporal cases are added.

## Verification
### Focused tests
- `python -m pytest -q tests/test_opening_movement_strategies.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_opening_range_retest_temporal_audit.py tests/test_candidate_phase2_ownership.py` -> `83 passed, 1 warning`
- `python -m pytest -q tests/test_trend_pullback_temporal_semantics.py tests/test_opening_movement_strategies.py` -> `29 passed, 1 warning`

### Static checks
- `python -m py_compile strategies/movement/opening_range_breakout.py tests/test_opening_movement_strategies.py tests/test_opening_range_retest_temporal_audit.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_candidate_phase2_ownership.py` -> pending

## Explicit non-claims
- No profitability or execution-readiness claim is made.
- No owner-store or Phase 2 repair was implemented.
- No strategy threshold or scoring formula change was introduced.
- No live broker behavior was exercised.
