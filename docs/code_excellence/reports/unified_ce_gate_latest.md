# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `6`
- total_findings: `11`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `4` | `0` |  |
| `cerberus` | `PASS` | `0` | `6` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `docs/agent_reviews/tradebuilder-fake-signals-fix.md`
- `strategies/trade_builder.py`
- `tests/test_feed_freshness_units.py`
- `tests/test_feed_health_epoch_missing.py`
- `tests/test_freshness_sla_stale_token_ratio.py`
- `tests/test_trade_builder_soft_vetoes.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_feed_freshness_units.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_health_epoch_missing.py` | `PASS` | `test_reality_accepted` |
| `tests/test_freshness_sla_stale_token_ratio.py` | `PASS` | `test_reality_accepted` |
| `tests/test_trade_builder_soft_vetoes.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/tradebuilder-fake-signals-fix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_freshness_units.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_health_epoch_missing.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_freshness_sla_stale_token_ratio.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_trade_builder_soft_vetoes.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/tradebuilder-fake-signals-fix.md` | `PASS` | `evidence_contract_satisfied` |
