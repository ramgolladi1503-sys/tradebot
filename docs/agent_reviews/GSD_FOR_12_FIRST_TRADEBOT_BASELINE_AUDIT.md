# GSD-FOR-12 — First TradeBot Baseline Audit

## Agent Work Contract

### Scope

Add the baseline-audit generator that creates the first TradeBot repo-forensics baseline evidence from a real checkout.

This PR does **not** fake a baseline report. The chat environment cannot clone/download the full repository archive, so the correct implementation is a safe baseline generation command that must be run from a real local checkout or CI checkout.

### Files Changed

- `tools/repo_forensics/baseline.py`
- `scripts/generate_repo_forensics_baseline.py`
- `tests/test_repo_forensics_baseline.py`
- `docs/agent_reviews/GSD_FOR_12_FIRST_TRADEBOT_BASELINE_AUDIT.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No fake baseline report.
- No merge automation.
- No test weakening.

## Baseline Command

Run from a real checkout:

```bash
python scripts/generate_repo_forensics_baseline.py --repo . --config .gsd-forensics.yaml
```

Default outputs:

```text
docs/repo_forensics/reports/baseline_latest.md
docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md
docs/repo_forensics/reports/baseline_pr_summary.md
```

## Why This PR Does Not Commit a Fake Baseline

A baseline audit must be generated from actual repository contents. The GitHub connector can read specific files but cannot provide a full executable checkout/archive to this environment.

So the honest path is:

1. Add the baseline generator.
2. Prove it with tests.
3. Run it from a real checkout/CI checkout.
4. Commit generated baseline artifacts after the command produces them.

## Approval Batching Model

This continues the low-friction model:

```text
many checks internally
one baseline gate externally
```

The baseline command runs the unified gate in report-only mode so it records current findings instead of hiding them by failing before files are written.

## Grill Me Review

### Challenge

A fake baseline would create fake confidence. A baseline must be generated from a real checkout, not manually invented.

### Findings

- Good: baseline generator uses the unified runner.
- Good: report-only exit policy writes evidence even if the current repo has FAIL/UNKNOWN findings.
- Good: generated files include baseline report, 3-agent evidence, and PR summary.
- Good: tests prove artifacts are written and hard failures are recorded.
- Risk: this PR adds the generator, but the actual baseline artifacts still need to be generated in a real checkout after merge or in a follow-up baseline artifact PR.

### Verdict

PASS — valid as baseline generation infrastructure. Do not claim a real baseline report exists until the command is run and artifacts are committed.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No scanner behavior changed.
- [x] No fake baseline committed.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The baseline generator invokes the existing static repo-forensics runner. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Baseline generator added.
- [x] Baseline CLI added.
- [x] Tests added for artifact generation and report-only hard-failure recording.
- [x] Next action is clear: run the command in a real checkout and commit the generated baseline artifacts.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Baseline generator module.
- Baseline CLI.
- Tests for generated report/evidence/summary artifacts.
- Evidence file for this PR.

### Out of Scope

- Fake baseline artifact.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Auto-PR.
- Dashboard execution.
- Product behavior changes.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No fake baseline.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — baseline generation infrastructure only.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR intentionally avoids fake generated baseline output.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover successful baseline artifact generation and hard-failure recording under report-only mode.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_baseline.py
```

Broader repo-forensics targeted set:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_architecture_drift.py tests/test_repo_forensics_unified_runner.py tests/test_repo_forensics_agent_evidence.py tests/test_repo_forensics_baseline.py
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-12B — Commit First Generated Baseline Artifacts

Expected next deliverables:

- run `python scripts/generate_repo_forensics_baseline.py --repo . --config .gsd-forensics.yaml` from a real checkout
- commit `docs/repo_forensics/reports/baseline_latest.md`
- commit `docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md`
- commit `docs/repo_forensics/reports/baseline_pr_summary.md`
- no target runtime execution


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
