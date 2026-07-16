# Strategy Truth: `opening_range_retest_v1` temporal repair

## Implementation Direction
`RIGHT_WITH_GAPS`

## Approved Objective
Convert `opening_range_retest_v1` from a snapshot-gated candidate generator into a causal completed-bar implementation using the existing completed-bar history contract, without changing strategy thresholds or downstream ownership.

## Final Verification Gate
The committed temporal producer at `0ff2ce450922ed39a1ffa989b57e16961bdfebb1` is present on branch `fix/opening-range-retest-temporal-implementation`, and fixture ancestry from `200c04994f718f01c4267f7272b8844353c7a0b9` is proven.

The remote-backup gate is blocked. The frozen opening-range tests pass, but required shared truth, adjacent temporal, and full repository suites still contain stale snapshot-era expectations and fixtures that do not provide `completed_bar_history`.

## Worktree And Branch
- worktree: `/Users/madhuram/tradebot-opening-range-retest-temporal-repair`
- branch: `fix/opening-range-retest-temporal-implementation`
- fixture base: `200c04994f718f01c4267f7272b8844353c7a0b9`
- repair commit: `0ff2ce450922ed39a1ffa989b57e16961bdfebb1`
- evidence commit: pending at time of this document edit

## Commit Graph
```text
* 0ff2ce45 strategy: salvage opening range temporal repair
* fe7add39 strategy: salvage opening range temporal repair
* 200c0499 test: complete opening range retest temporal fixture matrix
* a3e26867 strategy: add opening range retest temporal fixture evidence
* 8a5e3974 audit: freeze opening range retest temporal protocol
* 10f0c0d2 tests: certify trend pullback isolation controls
```

## Committed Paths
- `docs/agent_reviews/strategy_truth_opening_range_retest_temporal_repair.md`
- `strategies/movement/opening_range_breakout.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_opening_movement_strategies.py`
- `tests/test_opening_range_retest_temporal_audit.py`
- `tests/test_opening_range_retest_temporal_fixture_contract.py`

`runtime/strategy_validation/regime_timeline.jsonl` is unchanged at the committed repair HEAD. It was appended by the full-suite run and restored as generated test output before this evidence update.

## Production Behavior
### Current Call Chain
`strategies.strategy_registry.OPENING_RANGE_BREAKOUT` -> `strategies/movement/opening_range_breakout.py` -> `generate_opening_range_retest_candidates`

### Causal Contract
- `completed_bar_history` is required.
- Missing history emits no candidate and records `STRATEGY_EVIDENCE_BLOCKED`.
- Empty or short history emits no candidate.
- Malformed history emits no candidate.
- Snapshot fallback is absent.
- Opening range is recomputed from the first 15 completed one-minute bars.
- Supplied ORB fields are reconciliation inputs only.
- Supplied ORB fields may be absent when valid completed history exists.
- Supplied ORB mismatch blocks the candidate.
- CALL requires breakout above ORB high, later retest, and later continuation.
- PUT requires breakout below ORB low, later retest, and later continuation.
- Same-bar breakout/retest and same-bar retest/continuation are forbidden.
- Invalidation prevents revival of the old setup.
- A later fresh breakout creates a new setup identity.
- Later prefixes do not re-emit the same setup lineage.

## Lineage And Proposal Evidence
Valid CALL output field paths:
- contract version: `candidate.evidence["setup_identity"]["contract_version"]`
- setup id: `candidate.evidence["setup_identity"]["setup_id"]`
- history hash: `candidate.evidence["setup_identity"]["history_hash"]`
- proposal readiness: `candidate.evidence["setup_identity"]["proposal_ready_at_iso"]`
- breakout timestamp: `candidate.evidence["setup_identity"]["breakout_timestamp"]`
- retest timestamp: `candidate.evidence["setup_identity"]["retest_timestamp"]`
- continuation timestamp: `candidate.evidence["setup_identity"]["continuation_timestamp"]`
- direction: `candidate.evidence["setup_identity"]["direction"]`
- boundary type: `candidate.evidence["setup_identity"]["boundary_type"]`
- boundary value: `candidate.evidence["setup_identity"]["normalized_boundary_value"]`
- symbol: `candidate.evidence["setup_identity"]["symbol"]`
- session date: `candidate.evidence["setup_identity"]["session_date"]`

Direct sampled CALL evidence:
- status: `RAW_CANDIDATE`
- temporal lineage state: `candidate.lineage["promotion_state"] == "READY_FOR_PUBLICATION"`
- setup id: `cf91072a6283d3e1f298c06d4ad360297ae8e7e4360c13e2581f2bb0e70fda10`
- history hash: `0ef55f71302cf88edebf921168e73d6083c98c6208411e6387cbe5e065790b76`
- proposal ready at: `2026-07-14T09:34:00+05:30`
- breakout timestamp: `2026-07-14T09:31:00+05:30`
- retest timestamp: `2026-07-14T09:32:00+05:30`
- continuation timestamp: `2026-07-14T09:34:00+05:30`
- boundary: `ORB_HIGH=22600.0`
- symbol/session: `NIFTY` / `2026-07-14`

Direct sampled PUT evidence:
- status: `RAW_CANDIDATE`
- temporal lineage state: `candidate.lineage["promotion_state"] == "READY_FOR_PUBLICATION"`
- setup id: `5aee562ca42afc3c1f20cafe20b9f75f92953141d364549056a9a4571407a800`
- history hash: `15a5b5e81b2aeea703a5c7757576e52a25ccc033a43b93d080958b4aa4353100`
- proposal ready at: `2026-07-14T09:34:00+05:30`
- breakout timestamp: `2026-07-14T09:31:00+05:30`
- retest timestamp: `2026-07-14T09:33:00+05:30`
- continuation timestamp: `2026-07-14T09:34:00+05:30`
- boundary: `ORB_LOW=22500.0`
- symbol/session: `NIFTY` / `2026-07-14`

## Movement And Ownership Boundary
- `StrategyCandidate.status`: `RAW_CANDIDATE`
- temporal lineage state: `READY_FOR_PUBLICATION`
- owner state written: no
- outbox state written: no
- durable owner acceptance: not proven
- delivery acknowledgement: not proven
- authoritative single publication: not proven until owner integration

`RAW_CANDIDATE` is the existing movement-layer schema status. It does not prove durable owner acceptance.

## Score Provenance
Canonical causal CALL:
- raw score: `0.45150442477876107`
- confidence score: `0.45150442477876107`
- price structure score: `0.45150442477876107`
- regime input: `VOLATILITY_EXPANSION=0.45`

Lower-volatility control:
- raw score: `0.42150442477876104`
- source test: `tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level`
- root cause: same causal sequence with `VOLATILITY_EXPANSION=0.30` instead of `0.45`

Validated score `0.328053`:
- source tests include `tests/test_strategy_context_truth.py`, `tests/test_strategy_profile_fail_closed.py`, `tests/test_strategy_missing_evidence_policy.py`, `tests/test_strategy_missing_evidence_observability.py`, and `tests/test_strategy_registry_integrity.py`
- current status: not reconciled with the completed-history temporal producer
- failure mode: those tests still build snapshot-era contexts without `completed_bar_history`, so `opening_range_retest_v1` correctly blocks with `missing_required_temporal_evidence`
- classification: stale shared fixture/expectation, not a proven current movement-layer temporal score

## Stage-Specific Fingerprints
Movement-layer temporal candidate:
```text
opening_range_retest_v1
BUY_CALL
RAW_CANDIDATE
0.45150442477876107
opening_range_breakout_retest_hold
price_returns_inside_opening_range
opening range breakout retest held
READY_FOR_PUBLICATION
```

Validated candidate:
```text
0.328053 snapshot-era validated fingerprint remains present in shared tests,
but is not currently produced by `opening_range_retest_v1` without completed history.
```

## Verification Results
### Fixture Contract
```text
python -m pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py
44 passed, 1 warning
exit code 0
```

### Temporal Audit
```text
python -m pytest -q tests/test_opening_range_retest_temporal_audit.py
20 passed, 1 warning
exit code 0
```

### Opening Movement Tests
```text
python -m pytest -q tests/test_opening_movement_strategies.py
8 passed, 1 warning
exit code 0
```

### Ownership Tests
```text
python -m pytest -q tests/test_candidate_phase2_ownership.py
11 passed, 1 warning
exit code 0
```

### Shared Truth Tests
```text
python -m pytest -q tests/test_strategy_context_truth.py tests/test_strategy_profile_fail_closed.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py tests/test_strategy_missing_evidence_policy.py tests/test_strategy_missing_evidence_observability.py
13 failed, 64 passed, 1 warning
exit code 1
```

First shared-truth failure:
`tests/test_strategy_context_truth.py::test_direct_context_fingerprint_is_unchanged`

Root class:
shared fixtures still expect snapshot-era `opening_range_retest_v1` emission without `completed_bar_history`.

### Adjacent Temporal Tests
```text
python -m pytest -q tests/test_strategy_temporal_harness.py tests/test_trend_pullback_temporal_semantics.py tests/test_orb_ohlcv_validation.py tests/test_strategy_registry_integrity.py
6 failed, 49 passed, 1 warning
exit code 1
```

First adjacent failure:
`tests/test_orb_ohlcv_validation.py::test_layer_a_signals_are_causal_and_label_atr_proxy`

Root class:
ORB OHLCV validation layer does not provide the completed-bar history now required by the producer.

### Static Checks
```text
python -m py_compile <required files>
exit code 0

ruff check <required files>
All checks passed
exit code 0

git diff --check
exit code 0
```

### Full Suite
```text
python -m pytest -q
23 failed, 5875 passed, 1 deselected, 935 warnings
exit code 1
duration: 865.16s
```

First full-suite failure:
`tests/test_atr_contract_decision.py::test_candidate_fingerprints_remain_unchanged`

Known auth failure:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

The auth failure is present, but the full suite also has multiple opening-range related failures. Therefore the full repository status is not green and cannot be classified as only the known auth failure.

## Gate Decision
- fixture ancestry: proven
- committed paths: expected only
- runtime artifact at repair HEAD: unchanged
- frozen opening-range tests: pass
- shared truth tests: fail
- adjacent temporal tests: fail
- static checks: pass
- full suite: fail
- evidence document: finalized with blocked gate status
- push: blocked

## Explicit Non-Claims
- No owner integration is complete.
- Authoritative single publication is not proven.
- Candidate attrition is not resolved.
- TradeBuilder is not verified.
- Phase 1 and Phase 2 are not re-certified by this gate.
- No historical edge, profitability, execution readiness, live readiness, production certification, or complete Phase 3B closure is claimed.
