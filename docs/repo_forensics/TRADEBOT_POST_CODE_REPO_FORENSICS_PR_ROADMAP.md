# TradeBot Post-Code Repo Forensics — 14-PR Project Build Guide

Local/manual post-code evaluation architecture for TradeBot. Deterministic checks first. Evidence before confidence.

## 1. Project Purpose

Build a TradeBot-only post-code evaluation system that audits whether implemented code is actually wired, safe, testable, and evidence-backed after each PR.

This does **not** replace normal tests or the existing 3-agent pre-code discipline. It becomes the post-code truth gate.

The system must answer one brutal question:

> Does TradeBot actually run the systems we think we built?

## 2. Hard Boundaries

These boundaries are non-negotiable for the TradeBot-local version:

- No dashboard in MVP.
- No webhooks.
- No auto-fix.
- No auto-PR creation.
- No AI auto-agent execution.
- No broker calls.
- No executing target runtime/trading code.
- No mutation of TradeBot production logic by the auditor.
- No plug-and-play extraction until the TradeBot version proves useful findings.
- `UNKNOWN` is not `PASS`.

## 3. Repo Structure Target

```text
docs/repo_forensics/
  REPO_FORENSICS_ARCHITECTURE.md
  TRADEBOT_AUDIT_CHECKLIST.md
  AUDIT_REPORT_TEMPLATE.md
  FLOW_WIRING_TEMPLATE.md
  TEST_REALITY_TEMPLATE.md
  SAFETY_BOUNDARY_TEMPLATE.md
  EVIDENCE_AUDIT_TEMPLATE.md
  ARCHITECTURE_DRIFT_TEMPLATE.md
  reports/

docs/agent_reviews/
  templates/REPO_FORENSICS_AGENT_REVIEW_TEMPLATE.md

tools/repo_forensics/
  __init__.py
  cli.py
  config_loader.py
  repo_cartographer.py
  runtime_wiring.py
  import_graph.py
  critical_module_checker.py
  test_reality.py
  safety_boundary.py
  evidence_auditor.py
  architecture_drift.py
  report_writer.py

.gsd-forensics.yaml
scripts/run_repo_forensics.py
```

## 4. 14-PR Build Roadmap

| PR | Name | Purpose | Deliverables / Proof | Do Not Touch |
|---|---|---|---|---|
| GSD-FOR-01 | Repo Forensics Architecture Contract | Add architecture docs/templates and define audit lifecycle. | Architecture docs, audit checklist, report templates. | No scanner, no product-code changes. |
| GSD-FOR-02 | TradeBot Forensics Profile | Add `.gsd-forensics.yaml` declaring entrypoints, flows, safety modes, and evidence fields. | Config plus profile doc. | No generic package abstraction. |
| GSD-FOR-03 | Repo Cartographer Scanner | Scan files, entrypoints, tests, shell scripts, dashboards, runtime/evidence paths. | `latest_repo_map.md` plus scanner tests. | Do not import or execute TradeBot modules. |
| GSD-FOR-04 | Entrypoint and Runtime Wiring Audit | Check `run_live.sh`, `main.py`, dashboard wiring, and expected flow steps as PASS/FAIL/UNKNOWN. | `runtime_wiring_latest.md` plus tests. | Do not claim UNKNOWN as safe. |
| GSD-FOR-05 | Critical Module Caller Check | Detect critical modules that are tested but not production-called. | Import graph/caller report plus fixture tests. | Do not refactor target modules. |
| GSD-FOR-06 | Test Reality Classifier | Classify tests into shape-only, behavior, integration, safety, runtime, evidence, fake confidence, or unknown. | `test_reality_latest.md` plus classifier tests. | Do not weaken existing tests. |
| GSD-FOR-07 | Safety Boundary Auditor | Audit SIM/PAPER/LIVE and broker safety boundaries. | Safety findings plus forbidden-import fixture tests. | No broker imports or live execution. |
| GSD-FOR-08 | Evidence Auditor | Check runtime/evidence JSON/JSONL fields and traceability. | `evidence_latest.md` plus good/bad evidence fixtures. | Do not create fake runtime evidence. |
| GSD-FOR-09 | Architecture Drift Detector | Detect duplicate paths, stale docs, old/new pipeline splits, config drift. | Drift report plus fixture tests. | Do not delete or rewrite product code. |
| GSD-FOR-10 | Unified Forensics Runner | Add one local command to run all checks. | `make repo-forensics` or script output. | No CI blocking yet unless explicitly scoped. |
| GSD-FOR-11 | 3-Agent Evidence Integration | Add repo-forensics summary to PR template and agent review evidence. | Agent review template and PR summary section. | No external agent auto-calling. |
| GSD-FOR-12 | First TradeBot Baseline Audit | Run full audit against TradeBot and commit baseline report. | Full baseline report and top 5 fixes. | No product-code fixes in this PR. |
| GSD-FOR-13 | Forensics Gate for Future PRs | Make forensics part of future PR workflow. | Advisory/soft/strict gate policy. | Do not block CI prematurely. |
| GSD-FOR-14 | Product Reality Audit Layer | Add trading-quality checks after wiring tool proves useful. | Product reality report for fallback, ranking, scoring, candidate pool, and paper realism. | Do not start before first 13 are useful. |

## 5. Acceptance Rules for Every PR

Every PR in this roadmap must satisfy these rules:

- State files changed, design, risks, tests, evidence, and scope guard.
- Add fixture tests for every scanner/checker, including at least one negative case.
- Every finding must include severity, file path where possible, evidence, impact, recommendation, and proof required.
- No CRITICAL/HIGH finding should be ignored without an explicit waiver.
- Reports must separate proven facts from `UNKNOWN`.
- Post-code evaluation reports must be committed under `docs/repo_forensics/reports/` when scoped.
- No target runtime/trading code may be executed by the auditor.
- No broker or external API calls may be introduced.
- No production TradeBot behavior may be changed unless that PR explicitly scopes it. Most GSD-FOR PRs should be audit-only.

## 6. Severity Policy

| Severity | Meaning | Example |
|---|---|---|
| CRITICAL | Can cause unsafe/live/dangerous behavior. | Paper path imports live broker placement. |
| HIGH | Breaks core product promise. | Critical module has no production caller. |
| MEDIUM | Weakens reliability/evidence. | Required evidence field missing. |
| LOW | Maintainability concern. | Stale doc reference. |
| INFO | Helpful observation. | Module count summary. |
| UNKNOWN | Safety/correctness could not be proven. | Dynamic runtime path unclear. |

Hard rule:

> `UNKNOWN` is not safe. It means “not proven.”

## 7. First Five PRs Are Mandatory Before Anything Else

Do not start Product Reality, plug-and-play packaging, or AI interpretation before these five produce useful findings:

1. GSD-FOR-01 — Architecture Contract
2. GSD-FOR-02 — TradeBot Profile
3. GSD-FOR-03 — Repo Cartographer Scanner
4. GSD-FOR-04 — Entrypoint and Runtime Wiring Audit
5. GSD-FOR-05 — Critical Module Caller Check

If these first five do not reveal useful repo truth, expanding the system is just architecture theater.

## 8. Deferred Work

The following is deferred until TradeBot-local forensics proves useful:

- Extract into reusable plug-and-play package.
- Add algotradify adapter.
- Add optional AI interpretation.
- Add remediation suggestions.
- Add dashboard or visual UI.
- Add webhooks or external automation.
- Add auto-fix or auto-PR generation.

## 9. Final Operating Rule

This project exists to answer one question after every meaningful code change:

> Does TradeBot actually run the systems we think we built, safely and with evidence?

If the answer is not proven, the correct status is not “good enough.” The correct status is `UNKNOWN`, and `UNKNOWN` must be treated as a risk until proven.
