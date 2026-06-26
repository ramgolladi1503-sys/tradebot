# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `1`
- total_findings: `1`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `0` | `0` |  |
| `cerberus` | `PASS` | `0` | `1` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/htf_paper_telemetry.py`

## Minerva Findings

- No findings.

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/htf_paper_telemetry.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.
