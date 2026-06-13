# Repo Forensics — PR Gate

## Purpose

Compare current static repo-forensics output against the committed baseline.
Existing baseline debt is not treated as a new regression. Increases are flagged.

## Verdict

`PASS`

## Baseline Summary

- Hard failures: `141`
- Unknowns: `98`
- Warnings: `132`

## Current Summary

- Hard failures: `141`
- Unknowns: `98`
- Warnings: `132`
- Full report: `/Users/madhuram/tradebot/docs/repo_forensics/reports/pr_gate_latest.md`

## Delta Table

| Metric | Baseline | Current | Delta |
|---|---:|---:|---:|
| hard_failures | 141 | 141 | 0 |
| unknowns | 98 | 98 | 0 |
| warnings | 132 | 132 | 0 |
| missing_required_entrypoints | 4 | 0 | -4 |
| missing_critical_modules | 0 | 0 | 0 |
| runtime_flow_failures | 0 | 0 | 0 |
| runtime_flow_unknowns | 98 | 0 | -98 |
| critical_caller_missing | 0 | 0 | 0 |
| critical_caller_test_only | 0 | 4 | 4 |
| critical_caller_unreferenced | 0 | 1 | 1 |
| fake_confidence_tests | 132 | 115 | -17 |
| unknown_tests | 0 | 9 | 9 |
| safety_critical | 21 | 21 | 0 |
| safety_high | 0 | 81 | 81 |
| safety_unknown | 0 | 0 | 0 |
| evidence_high | 116 | 116 | 0 |
| evidence_medium | 0 | 16 | 16 |
| evidence_unknown | 0 | 0 | 0 |
| drift_high | 0 | 0 | 0 |
| drift_medium | 0 | 1 | 1 |
| drift_unknown | 0 | 7 | 7 |

## Gate Policy

- New hard failures: `FAIL`.
- New unknowns without new hard failures: `UNKNOWN`.
- New warnings only: `PASS_WITH_WARNINGS`.
- Same or improved counts: `PASS`.

## Scope Guard

- Static scan only.
- No target runtime execution.
- No broker calls.
- No live order actions.
- No auto-fix.
- No auto-PR.
