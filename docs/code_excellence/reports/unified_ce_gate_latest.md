# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `13`
- total_findings: `16`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `2` | `0` |  |
| `cerberus` | `PASS` | `0` | `13` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/math/__init__.py`
- `core/math/fractional_differentiation.py`
- `core/math/hmm_regime.py`
- `core/math/kalman_filter.py`
- `core/math/mean_reversion.py`
- `core/math/vpin.py`
- `core/regime_classifier.py`
- `docs/agent_reviews/quant_research_master_pr.md`
- `ml/trade_predictor.py`
- `strategies/pairs_arbitrage.py`
- `strategies/vwap_orb.py`
- `tests/test_core_math.py`
- `tests/test_quant_math.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_core_math.py` | `PASS` | `test_reality_accepted` |
| `tests/test_quant_math.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/math/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/math/fractional_differentiation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/math/hmm_regime.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/math/kalman_filter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/math/mean_reversion.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/math/vpin.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/regime_classifier.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/quant_research_master_pr.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `ml/trade_predictor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/pairs_arbitrage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/vwap_orb.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_core_math.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_quant_math.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/quant_research_master_pr.md` | `PASS` | `evidence_contract_satisfied` |
