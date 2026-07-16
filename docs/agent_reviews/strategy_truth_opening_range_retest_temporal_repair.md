# Strategy Truth: `opening_range_retest_v1` temporal repair

## Implementation direction
`RIGHT_WITH_GAPS`

## Approved objective
Convert `opening_range_retest_v1` from a snapshot-gated candidate generator into a causal completed-bar implementation using the existing completed-bar history contract, without changing strategy thresholds or downstream ownership.

## What was implemented
- `strategies/movement/opening_range_breakout.py` now requires `completed_bar_history`.
- The strategy recomputes ORB high/low from the first 15 completed one-minute bars.
- Supplied ORB values are only reconciliation inputs; mismatches fail closed with deterministic blocked evidence.
- The strategy scans completed bars causally for breakout, retest, and continuation.
- The strategy emits only on the first qualifying continuation for a setup lineage, not on later prefixes that merely extend the same move.
- Proposal evidence now carries `setup_identity` with `contract_version`, `setup_id`, `history_hash`, and `proposal_ready_at_iso`.
- Short or missing history still falls back to the existing snapshot contract so the accepted direct-context control remains stable.
- Test fixtures and audit tests now use causal completed-history inputs where they are asserting positive behavior.

## Architecture change
`NECESSARY_MINIMAL`

## Starting head
`200c04994f718f01c4267f7272b8844353c7a0b9`

## Final head
`pending commit`

## Files changed
- `strategies/movement/opening_range_breakout.py`
- `tests/test_opening_movement_strategies.py`
- `tests/test_opening_range_retest_temporal_audit.py`
- `tests/test_opening_range_retest_temporal_fixture_contract.py`
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
- Once a setup is qualified, later prefixes do not re-emit the same setup lineage.

### Blocked evidence examples
- Missing ORB inputs in the snapshot fallback emit `event=STRATEGY_EVIDENCE_BLOCKED ... reason=missing_required_orb_evidence`.
- ORB mismatch emits `event=STRATEGY_EVIDENCE_BLOCKED ... reason=invalid_orb_reconciliation`.

## Candidate fingerprints
### Canonical causal CALL control
- `opening_range_retest_v1`
- `BUY_CALL`
- `RAW_CANDIDATE`
- `0.451504`
- `opening_range_breakout_retest_hold`
- `price_returns_inside_opening_range`
- `opening range breakout retest held`

### Trend-pullback control with causal opening-range history
- `opening_range_retest_v1`
- `BUY_CALL`
- `RAW_CANDIDATE`
- `0.421504`
- `opening_range_breakout_retest_hold`
- `price_returns_inside_opening_range`
- `opening range breakout retest held`

## Behavior preserved
- Strategy ID and movement type remain unchanged.
- CALL and PUT directional support remain unchanged.
- Pattern scoring formula remains unchanged.
- No broker, order, execution, feed, or profile wiring changed.
- `NO_TRADE_CHOP` and other unrelated strategies were not modified.

## Behavior changed
- Snapshot-only evaluation is now explicitly preserved as the accepted control path for short histories, while the causal 15-bar path remains visible through `setup_identity`.
- The strategy re-emits the snapshot fallback on short prefixes; the temporal harness now records that behavior instead of treating it as causal proof.
- `setup_identity` and causal history lineage are now visible in evidence.

## Risk assessment
- The implementation is still a narrow temporal repair. It does not claim profitability or production readiness.
- Remaining risk is limited to future contract drift in the surrounding fixture tests if more temporal cases are added.

## Verification
### Focused tests
- `python -m pytest -q tests/test_opening_movement_strategies.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_opening_range_retest_temporal_audit.py` -> `72 passed`
- `python -m pytest -q tests/test_strategy_temporal_harness.py tests/test_trend_pullback_temporal_semantics.py tests/test_opening_movement_strategies.py` -> `39 passed`

### Static checks
- `python -m py_compile strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_opening_range_retest_temporal_audit.py tests/test_trend_pullback_temporal_semantics.py` -> `0`

## Explicit non-claims
- No profitability or execution-readiness claim is made.
- No owner-store or Phase 2 repair was implemented.
- No strategy threshold or scoring formula change was introduced.
- No live broker behavior was exercised.
