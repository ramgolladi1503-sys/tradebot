# Repo Forensics — PR Gate

## Purpose

Compare current static repo-forensics output against the committed baseline.
Existing baseline debt is not treated as a new regression. Increases are flagged.

## Verdict

`PASS`

## Baseline Summary

- Hard failures: `25`
- Unknowns: `97`
- Warnings: `129`

## Current Summary

- Hard failures: `25`
- Unknowns: `97`
- Warnings: `129`
- Full report: `/Users/madhuram/tradebot/docs/repo_forensics/reports/pr_gate_latest.md`

## Delta Table

| Metric | Baseline | Current | Delta |
|---|---:|---:|---:|
| hard_failures | 25 | 25 | 0 |
| unknowns | 97 | 97 | 0 |
| warnings | 129 | 129 | 0 |
| missing_required_entrypoints | 0 | 0 | 0 |
| missing_critical_modules | 0 | 0 | 0 |
| runtime_flow_failures | 0 | 0 | 0 |
| runtime_flow_unknowns | 0 | 0 | 0 |
| critical_caller_missing | 0 | 0 | 0 |
| critical_caller_test_only | 4 | 4 | 0 |
| critical_caller_unreferenced | 1 | 1 | 0 |
| fake_confidence_tests | 114 | 114 | 0 |
| unknown_tests | 8 | 8 | 0 |
| safety_critical | 21 | 21 | 0 |
| safety_high | 81 | 81 | 0 |
| safety_unknown | 0 | 0 | 0 |
| evidence_high | 0 | 0 | 0 |
| evidence_medium | 14 | 14 | 0 |
| evidence_unknown | 0 | 0 | 0 |
| drift_high | 0 | 0 | 0 |
| drift_medium | 1 | 1 | 0 |
| drift_unknown | 7 | 7 | 0 |

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

## Agent Work Contract
## Grill Me Review
## Hermes Review
## GSD Review
## QA / Safety Review
## Acceptance Proof
## Runtime Proof Required After Merge
## What This PR Does Not Prove
## Human Approval
## High-Risk Path Review
