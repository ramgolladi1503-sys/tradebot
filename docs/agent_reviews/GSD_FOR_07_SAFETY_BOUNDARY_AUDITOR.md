# GSD-FOR-07 — Safety Boundary Auditor

## Agent Work Contract

### Scope

Add a static safety boundary auditor to the existing repo-forensics gate.

This PR extends the single local runner so it can scan source files for broker/order-action boundary risks, SIM/PAPER/LIVE leakage signals, read-only action-field violations, and live-mode default risks.

### Files Changed

- `tools/repo_forensics/safety_boundary.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_safety_boundary.py`
- `docs/agent_reviews/GSD_FOR_07_SAFETY_BOUNDARY_AUDITOR.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
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
6. Report Writer

## Safety Checks Added

The scanner flags:

- order-action calls such as `p_lace_order`, `m_odify_order`, `c_ancel_order`, `e_xit_order`
- broker-adjacent imports in paper/SIM/read-only paths
- `i-s_order_action=True`
- `b-roker_api_called=True`
- `l-ive_order_action=True`
- `b-roker_order_action=True`
- LIVE mode defaults outside scoped live startup paths
- repo-forensics tooling referencing runtime/broker modules

## Grill Me Review

### Challenge

A static safety scan can create false positives and must not pretend every flagged string is a real live risk.

### Findings

- Good: scanner reports findings only; it does not patch or auto-fix.
- Good: CRITICAL is reserved for paper/SIM/read-only/repo-forensics order-action risks.
- Good: report distinguishes CRITICAL/HIGH/MEDIUM/UNKNOWN.
- Risk: heuristic scan may flag false positives. That is acceptable because follow-up triage belongs in later Ariadne/Daedalus flow.

### Verdict

PASS — valid for GSD-FOR-07 as static safety boundary detection.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No runtime scripts changed except local forensics runner.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The auditor parses source files as text/AST. It does not import or execute TradeBot runtime modules and does not call any broker APIs.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Safety boundary auditor added.
- [x] Report writer includes safety boundary section.
- [x] Existing runner invokes cartography + wiring + caller checks + test reality + safety together.
- [x] Tests added for paper order-action flagging, read-only action-field flagging, and safe file behavior.
- [x] Next action is clear: GSD-FOR-08 Evidence Auditor.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static safety boundary scan.
- Forbidden order-action pattern detection.
- Read-only action-field checks.
- Runner integration.
- Report integration.
- Tests for safety behavior.

### Out of Scope

- Runtime safety execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Evidence auditor.
- Architecture drift detector.
- Ariadne/Daedalus/Vulcan implementation.
- Trade quality intelligence.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — narrow safety boundary auditor implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR detects static safety risks only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover critical safety patterns and safe no-finding behavior.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-08 — Evidence Auditor

Expected next deliverables:

- evidence field scanner
- weak evidence detection
- decision traceability checks
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
