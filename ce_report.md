# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `22`
- total_findings: `29`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `7` | `0` |  |
| `cerberus` | `PASS` | `0` | `22` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/opportunity_scoring.py`
- `core/strategy_parameter_profiles.py`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`
- `strategies/movement/_utils.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/event_volatility_expansion.py`
- `strategies/movement/exhaustion_reversal.py`
- `strategies/movement/failed_breakout_trap.py`
- `strategies/movement/late_day_momentum.py`
- `strategies/movement/mean_reversion_extension.py`
- `strategies/movement/opening_drive.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/option_pressure.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/vwap_reclaim.py`
- `tests/test_candidate_pool.py`
- `tests/test_fallback_never_executable.py`
- `tests/test_opportunity_scoring.py`
- `tests/test_opportunity_scoring_regime_profile_opt_in.py`
- `tests/test_strategy_generators_lineage.py`
- `tests/test_strategy_parameter_profiles.py`
- `tests/test_strategy_promotion_state.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_candidate_pool.py` | `PASS` | `test_reality_accepted` |
| `tests/test_fallback_never_executable.py` | `PASS` | `test_reality_accepted` |
| `tests/test_opportunity_scoring.py` | `PASS` | `test_reality_accepted` |
| `tests/test_opportunity_scoring_regime_profile_opt_in.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_generators_lineage.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_parameter_profiles.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_promotion_state.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/opportunity_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_parameter_profiles.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/audits/strategy_contract_and_edge_readiness_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/_utils.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/compression_breakout.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/event_volatility_expansion.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/exhaustion_reversal.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/failed_breakout_trap.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/late_day_momentum.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/mean_reversion_extension.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/opening_drive.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/opening_range_breakout.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/option_pressure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/trend_pullback.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/vwap_reclaim.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_pool.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_fallback_never_executable.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_opportunity_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_opportunity_scoring_regime_profile_opt_in.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_generators_lineage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_parameter_profiles.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_promotion_state.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.
