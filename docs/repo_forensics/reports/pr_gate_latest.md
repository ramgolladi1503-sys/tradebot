# Repo Forensics — PR Gate

## Purpose

Compare current static repo-forensics output against the committed baseline.
Existing baseline debt is not treated as a new regression. Increases are flagged.

## Verdict

`PASS_WITH_WARNINGS`

## Baseline Summary

- Hard failures: `113`
- Unknowns: `59`
- Warnings: `135`

## Current Summary

- Hard failures: `113`
- Unknowns: `52`
- Warnings: `139`
- Full report: `/Users/madhuram/tradebot/docs/repo_forensics/reports/pr_gate_latest.md`

## Delta Table

| Metric | Baseline | Current | Delta |
|---|---:|---:|---:|
| hard_failures | 113 | 113 | 0 |
| unknowns | 59 | 52 | -7 |
| warnings | 135 | 139 | 4 |
| missing_required_entrypoints | 9 | 0 | -9 |
| missing_critical_modules | 0 | 0 | 0 |
| runtime_flow_failures | 0 | 0 | 0 |
| runtime_flow_unknowns | 59 | 0 | -59 |
| critical_caller_missing | 0 | 0 | 0 |
| critical_caller_test_only | 0 | 4 | 4 |
| critical_caller_unreferenced | 0 | 1 | 1 |
| fake_confidence_tests | 135 | 122 | -13 |
| unknown_tests | 0 | 8 | 8 |
| safety_critical | 16 | 21 | 5 |
| safety_high | 0 | 36 | 36 |
| safety_unknown | 0 | 0 | 0 |
| evidence_high | 88 | 88 | 0 |
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
