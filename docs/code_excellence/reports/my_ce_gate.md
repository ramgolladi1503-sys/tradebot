# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `3`
- total_findings: `11`
- total_blocks: `8`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `0` | `0` |  |
| `cerberus` | `PASS` | `0` | `3` | `0` |  |
| `evidence` | `BLOCK` | `1` | `8` | `8` |  |

## Changed Paths

- `config/config.py`
- `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md`
- `strategies/trade_builder.py`

## Minerva Findings

- No findings.

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `config/config.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/fix-latency-and-mean-revert-20260613.md` | `BLOCK` | `required_evidence_field_missing` |

## Failed Gates

- `evidence` failed with exit_code `1`: blocked findings present
