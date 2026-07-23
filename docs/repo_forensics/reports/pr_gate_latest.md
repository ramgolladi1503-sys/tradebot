# Repo Forensics — PR Gate

## Purpose

Compare current static repo-forensics output against the committed baseline.
Existing baseline debt is not treated as a new regression. Increases are flagged.

## Verdict

`UNKNOWN`

## Baseline Summary

- Hard failures: `119`
- Unknowns: `167`
- Warnings: `124`

## Current Summary

- Hard failures: `115`
- Unknowns: `177`
- Warnings: `99`
- Full report: `/Users/madhuram/tradebot-constituent-lead-lag-v1/docs/repo_forensics/reports/pr_gate_latest.md`

## Delta Table

| Metric | Baseline | Current | Delta |
|---|---:|---:|---:|
| hard_failures | 119 | 115 | -4 |
| unknowns | 167 | 177 | 10 |
| warnings | 124 | 99 | -25 |
| missing_required_entrypoints | 4 | 0 | -4 |
| missing_critical_modules | 0 | 0 | 0 |
| runtime_flow_failures | 0 | 0 | 0 |
| runtime_flow_unknowns | 167 | 0 | -167 |
| critical_caller_missing | 0 | 0 | 0 |
| critical_caller_test_only | 0 | 4 | 4 |
| critical_caller_unreferenced | 0 | 1 | 1 |
| fake_confidence_tests | 124 | 98 | -26 |
| unknown_tests | 0 | 8 | 8 |
| safety_critical | 23 | 23 | 0 |
| safety_high | 0 | 161 | 161 |
| safety_unknown | 0 | 0 | 0 |
| evidence_high | 92 | 88 | -4 |
| evidence_medium | 0 | 0 | 0 |
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
