# GSD-FOR-08 — Evidence Auditor

## Agent Work Contract

### Scope

Add a static evidence auditor to the existing repo-forensics gate.

This PR extends the single local runner so it can scan configured evidence/report paths for weak proof and missing required decision/evidence fields.

### Files Changed

- `tools/repo_forensics/evidence_auditor.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_evidence_auditor.py`
- `docs/agent_reviews/GSD_FOR_08_EVIDENCE_AUDITOR.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No evidence mutation.
- No merge automation.
- No test weakening.

## Approval Batching Model

This continues the low-friction model:

```text
many checks internally
one local gate externally
```

Single command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

The command now runs:

1. Repo Cartographer
2. Runtime Wiring Auditor
3. Critical Module Caller Check
4. Test Reality Classifier
5. Safety Boundary Auditor
6. Evidence Auditor
7. Report Writer

## Evidence Checks Added

The scanner flags:

- status-only proof such as `{"status":"ok","safe":true}`
- invalid JSON/JSONL evidence files
- decision-like records missing required fields
- missing `reason`
- missing `is_order_action`
- missing `broker_api_called`
- text evidence containing weak ok/safe claims without decision traceability

## Grill Me Review

### Challenge

Evidence scanning can create false positives if it treats every JSON file as a decision record.

### Findings

- Good: only decision-like records are required to contain all decision fields.
- Good: status-only evidence is flagged as weak proof.
- Good: scanner reads configured evidence paths from `.gsd-forensics.yaml` instead of hardcoding paths.
- Risk: Markdown evidence validation remains heuristic. That is acceptable for this PR.

### Verdict

PASS — valid for GSD-FOR-08 as static evidence-quality detection.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No runtime scripts changed except local forensics runner.
- [x] No evidence files mutated by scanner.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The auditor reads files only. It does not import or execute TradeBot runtime modules and does not call any broker APIs.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Evidence auditor added.
- [x] Report writer includes evidence audit section.
- [x] Existing runner invokes cartography + wiring + caller checks + test reality + safety + evidence together.
- [x] Tests added for missing fields, weak status-only proof, and complete decision records.
- [x] Next action is clear: GSD-FOR-09 Architecture Drift Detector.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static evidence scan.
- Required field checks for decision-like records.
- Weak evidence detection.
- Runner integration.
- Report integration.
- Tests for evidence behavior.

### Out of Scope

- Mutating evidence files.
- Generating runtime evidence.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Architecture drift detector.
- Ariadne/Daedalus/Vulcan implementation.
- Trade quality intelligence.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No evidence mutation.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — narrow evidence auditor implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR detects static evidence-quality risks only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover missing decision fields, weak status-only evidence, and complete decision records.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-09 — Architecture Drift Detector

Expected next deliverables:

- duplicate/stale/conflicting path detection
- old/new pipeline split detection
- dashboard reader drift checks
- no target runtime execution
