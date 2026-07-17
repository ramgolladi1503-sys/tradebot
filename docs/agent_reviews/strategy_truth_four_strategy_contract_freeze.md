# Four Strategy Contract Freeze

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Freeze and version four current strategy contracts for historical validation without changing production strategy code.

WHAT WAS ACTUALLY IMPLEMENTED:
Added a machine-readable contract bundle at [`docs/agent_reviews/four_strategy_contract_bundle.json`](./four_strategy_contract_bundle.json) and a matching evidence note. The bundle captures the current repository truth for `opening_range_retest_v1`, `compression_breakout_v1`, `trend_pullback_v1`, and `vwap_reclaim_rejection_v1`, including source hashes, profile resolution, required context fields, and the current frozen candidate fingerprints. No production code changed.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING HEAD:
`94b48666d166c45e4b65679b4811aa1ddc237b46`

BRANCH:
`fix/four-strategy-contract-freeze`

## Bundle Summary

The frozen bundle is intentionally narrow:

- It is historical-validation-only.
- It does not claim profitability, live readiness, or production certification.
- It does not change strategy formulas, thresholds, runtime context propagation, or phase ownership.

## Frozen Contracts

| strategy_id | runtime_strategy_id | contract_version | profile resolution | frozen fingerprint |
| --- | --- | --- | --- | --- |
| `OPENING_RANGE_RETEST` | `opening_range_retest_v1` | `opening_range_retest_temporal_v1` | `COMPATIBILITY_ALIAS` -> `opening_range_breakout_v1` | `opening_range_retest_v1 / BUY_CALL / RAW_CANDIDATE / 0.42150442477876104` |
| `COMPRESSION_BREAKOUT` | `compression_breakout_v1` | `n/a` | `EXACT_PROFILE` | `compression_breakout_v1 / BUY_CALL / RAW_CANDIDATE / 0.470676` |
| `TREND_PULLBACK` | `trend_pullback_v1` | `trend_pullback_temporal_v1` | `EXACT_PROFILE` | `trend_pullback_v1 / BUY_CALL / RAW_CANDIDATE / 0.648584` |
| `VWAP_RECLAIM_REJECTION` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_causal_v1` | `EXACT_PROFILE` | `vwap_reclaim_rejection_v1 / BUY_CALL / RAW_CANDIDATE / 0.392377` |

## Provenance

The bundle records the exact source hashes for:

- `config/strategy_inventory.yml`
- `core/movement_contract.py`
- `core/strategy_parameter_profiles.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/vwap_reclaim.py`

## Proof Tests

The freeze is backed by existing repo truth and a new focused bundle test. Relevant proof lanes include:

- `tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level`
- `tests/test_candidate_phase2_ownership.py::test_generators_preserve_setup_identity_and_pattern_scores`
- `tests/test_vwap_reclaim_runtime_conformance.py::test_vwap_reclaim_runtime_uses_canonical_vwap_not_final_close`
- `tests/test_vwap_reclaim_temporal_conformance.py::test_vwap_reclaim_runtime_and_direct_fingerprints_match_for_causal_snapshot`
- `tests/test_strategy_registry_integrity.py::test_fixed_candidate_fingerprint_matches_phase0_baseline`

## Explicit Non-Claims

- No historical edge claim.
- No profitability claim.
- No live-readiness claim.
- No execution-readiness claim.
- No production certification claim.
