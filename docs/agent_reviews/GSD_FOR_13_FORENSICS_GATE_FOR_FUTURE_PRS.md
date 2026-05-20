# GSD-FOR-13 — Forensics Gate for Future PRs

## Agent Work Contract

### Scope

Add a baseline-aware repo-forensics PR gate.

This PR makes the committed baseline useful by comparing current scanner output against baseline counts. Existing known debt is not treated as a new regression. Increases are flagged.

### Files Changed

- `tools/repo_forensics/pr_gate.py`
- `scripts/run_repo_forensics_pr_gate.py`
- `tests/test_repo_forensics_pr_gate.py`
- `docs/agent_reviews/GSD_FOR_13_FORENSICS_GATE_FOR_FUTURE_PRS.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No merge automation.
- No scanner behavior changes.
- No baseline mutation.
- No test weakening.

## Gate Command

Run from a real checkout:

```bash
PYTHONPATH=. python scripts/run_repo_forensics_pr_gate.py --repo . --config .gsd-forensics.yaml
```

Default baseline input:

```text
docs/repo_forensics/reports/baseline_pr_summary.md
```

Default report output:

```text
docs/repo_forensics/reports/pr_gate_latest.md
```

## Gate Policy

| Condition | Verdict |
|---|---|
| New hard failures | FAIL |
| No new hard failures, but new unknowns | UNKNOWN |
| No new hard failures/unknowns, but new warnings | PASS_WITH_WARNINGS |
| Same or improved counts | PASS |

## Why This Matters

The baseline currently records known debt:

```text
hard_failures=113
unknowns=59
warnings=135
```

Future PRs should not be blocked just because the baseline is ugly. They should be blocked when they make the situation worse.

## Grill Me Review

### Challenge

A baseline-aware gate can hide debt if it treats the baseline as acceptable forever.

### Findings

- Good: the gate only prevents new regressions.
- Good: it does not claim baseline findings are acceptable long-term.
- Good: current output is still written in report-only mode so the full current report exists.
- Good: new hard failures fail the gate.
- Risk: the compact baseline summary contains aggregate counts, not every granular metric. That is acceptable for this PR, but future enhancement can compare detailed findings if needed.

### Verdict

PASS — valid for GSD-FOR-13 as future-PR regression protection.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No scanner behavior changed.
- [x] No baseline mutation.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The PR gate invokes the existing static repo-forensics runner in report-only mode. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Baseline parser added.
- [x] Delta comparison added.
- [x] Gate verdict policy added.
- [x] PR gate report renderer added.
- [x] PR gate CLI added.
- [x] Tests added for baseline parsing, verdict policy, and report generation.
- [x] Next action is clear: GSD-FOR-14 Product Reality Audit Layer.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Baseline-aware comparison.
- Future PR gate verdict policy.
- PR gate report generation.
- PR gate CLI.
- Tests for gate behavior.

### Out of Scope

- Fixing baseline debt.
- Mutating baseline files.
- Auto-fix.
- Auto-PR.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Product behavior changes.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No scanner behavior changes.
- [x] No baseline mutation.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — future PR regression gate only.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR compares baseline/current counts and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover baseline parsing, delta verdicts, and report rendering.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_pr_gate.py
```

Broader repo-forensics targeted set:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_architecture_drift.py tests/test_repo_forensics_unified_runner.py tests/test_repo_forensics_agent_evidence.py tests/test_repo_forensics_baseline.py tests/test_repo_forensics_pr_gate.py
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-14 — Product Reality Audit Layer

Expected next deliverables:

- product capability vs proof classification
- mocked/theoretical/proven separation
- no target runtime execution
- no broker calls
