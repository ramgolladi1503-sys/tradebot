# Repo Forensics Architecture

## Purpose

TradeBot repo forensics is a local/manual post-code evaluation system. It audits whether implemented code is actually wired, safe, testable, evidence-backed, and aligned with the intended runtime flow.

It does not replace normal tests. It runs after code exists and before the PR is treated as trustworthy.

## Core Question

> Does TradeBot actually run the systems we think we built, safely and with evidence?

If the answer cannot be proven, the status is `UNKNOWN`, not `PASS`.

## Hard Boundaries

- No broker calls.
- No live order placement.
- No target runtime execution.
- No dashboard, webhook, auto-fix, auto-PR, or external agent automation in MVP.
- No mutation of TradeBot production behavior by the forensics tool.
- No silent fallback on invalid config.
- No treating `UNKNOWN` as safe.

## Architecture Layers

```text
TradeBot Repository
  -> .gsd-forensics.yaml
  -> Repo Cartographer / Argus
  -> Runtime Wiring Auditor / Atlas
  -> Test Reality Classifier / Minerva
  -> Safety Boundary Auditor / Cerberus
  -> Evidence Auditor
  -> Architecture Drift Detector
  -> Markdown Evidence Reports
```

## Components

| Component | Responsibility |
|---|---|
| Config Loader | Loads `.gsd-forensics.yaml` and fails closed on invalid config. |
| Repo Cartographer | Indexes files, entrypoints, tests, scripts, runtime/evidence paths. |
| Import Graph | Builds static import relationships without importing TradeBot modules. |
| Runtime Wiring Auditor | Checks configured runtime flow steps as PASS / FAIL / UNKNOWN. |
| Critical Module Checker | Detects critical modules with no proven production caller. |
| Test Reality Classifier | Separates shape-only tests from real behavior/safety/evidence proof. |
| Safety Boundary Auditor | Checks SIM/PAPER/LIVE and broker boundary risks. |
| Evidence Auditor | Checks whether logs/reports contain traceable decision evidence. |
| Architecture Drift Detector | Finds duplicate, stale, conflicting, or legacy paths. |
| Report Writer | Writes stable Markdown reports under `docs/repo_forensics/reports/`. |

## Required Reports

```text
docs/repo_forensics/reports/latest.md
docs/repo_forensics/reports/repo_map_latest.md
docs/repo_forensics/reports/runtime_wiring_latest.md
docs/repo_forensics/reports/test_reality_latest.md
docs/repo_forensics/reports/safety_boundary_latest.md
docs/repo_forensics/reports/evidence_latest.md
```

## Severity Policy

| Severity | Meaning |
|---|---|
| CRITICAL | Can cause unsafe/live/dangerous behavior. |
| HIGH | Breaks a core product or safety promise. |
| MEDIUM | Weakens reliability, test quality, or evidence. |
| LOW | Maintainability or clarity issue. |
| INFO | Non-blocking observation. |
| UNKNOWN | Could not prove safety/correctness. Not safe by default. |

## PR Integration

Every future PR using repo forensics must include:

```text
Repo Forensics Summary:
- Critical:
- High:
- Medium:
- Unknown:
- New findings:
- Resolved findings:
- Accepted unknowns:
- Evidence report path:
```

## GSD-FOR-01 Acceptance

This architecture contract is complete when the repo contains:

- architecture overview
- TradeBot audit checklist
- report templates
- flow wiring template
- test reality template
- safety boundary template
- evidence audit template
- architecture drift template
- agent review template
- GSD-FOR-01 evidence file
