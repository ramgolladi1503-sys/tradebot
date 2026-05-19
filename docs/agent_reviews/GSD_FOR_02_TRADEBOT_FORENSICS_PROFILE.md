# GSD-FOR-02 — TradeBot Forensics Profile

## Agent Work Contract

### Scope

Add the TradeBot-specific repo-forensics profile and agent parameter calibration.

This PR defines the parameters that all current and planned agents must use before scanner implementation begins.

### Files Changed

- `.gsd-forensics.yaml`
- `docs/repo_forensics/TRADEBOT_PROFILE.md`
- `docs/repo_forensics/AGENT_PARAMETER_CALIBRATION.md`
- `docs/agent_reviews/GSD_FOR_02_TRADEBOT_FORENSICS_PROFILE.md`

### Hard Boundaries

- No product code changes.
- No scanner implementation.
- No runtime execution.
- No dashboard changes.
- No broker/live behavior.
- No auto-fix or auto-PR behavior.
- No test changes.

### Expected Proof

- Profile declares required entrypoints.
- Profile declares critical modules.
- Profile declares expected runtime flows.
- Profile declares all agent parameters.
- Profile declares safety and evidence rules.
- Calibration document defines severity, confidence, handoff, tripwire, and merge policies.

## Grill Me Review

### Challenge

Agent names without parameters are fake structure. The profile must make agents stricter and more useful, not busier.

### Findings

- Good: all planned agents have explicit missions and required outputs.
- Good: TradeBot runtime entrypoints and critical modules are configured.
- Good: fallback/ranking/execution safety are first-class watch areas.
- Good: Ariadne/Daedalus/Vulcan handoff is constrained.
- Good: calibration doc prevents vague PASS results.
- Risk: these parameters are not executed until GSD-FOR-03+ implements scanner/config loading.

### Verdict

PASS — valid as parameter/profile PR only.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced in executable code.
- [x] No live behavior introduced.
- [x] No dashboard behavior changed.
- [x] No runtime scripts changed.
- [x] No tests changed.
- [x] No scanner implementation introduced.

### Safety Verification

The profile explicitly protects:

- broker calls
- live order actions
- SIM/PAPER/LIVE boundaries
- dashboard order actions
- read-only non-action fields
- evidence traceability

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Purpose is clear.
- [x] Scope is narrow.
- [x] Parameters are project-specific.
- [x] Calibration rules are defined.
- [x] Next action is clear: GSD-FOR-03 Repo Cartographer Scanner.

### Verdict

PASS.

## Scope Guard

### In Scope

- `.gsd-forensics.yaml`
- TradeBot profile documentation
- agent parameter calibration
- GSD-FOR-02 evidence file

### Out of Scope

- scanner code
- import graph implementation
- runtime wiring scanner
- product code
- strategy code
- dashboard behavior
- broker/live code
- tests

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target repo mutation by scanner.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No external agent automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — profile/configuration only.

### Gate 2 — Truth and Root-Cause

PASS — not an RCA PR; profile includes future RCA rules and confidence calibration.

### Gate 3 — Hardening and Proof

PASS — not a code-hardening PR; profile defines future hardening gates.

## Evidence

### Commands Run

No runtime/test commands required. Documentation/configuration-only PR.

### Files Produced

- `.gsd-forensics.yaml`
- `docs/repo_forensics/TRADEBOT_PROFILE.md`
- `docs/repo_forensics/AGENT_PARAMETER_CALIBRATION.md`
- `docs/agent_reviews/GSD_FOR_02_TRADEBOT_FORENSICS_PROFILE.md`

## Final Verdict

PASS — GSD-FOR-02 is complete as a TradeBot-specific forensics profile and agent-parameter calibration PR.

## Next PR

GSD-FOR-03 — Repo Cartographer Scanner

Expected next deliverables:

- `tools/repo_forensics/__init__.py`
- `tools/repo_forensics/config_loader.py`
- `tools/repo_forensics/repo_cartographer.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- tests using fixture repo data
- first repo map report format
