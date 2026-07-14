# GSD-FOR-03 — Repo Cartographer Scanner

## Agent Work Contract

### Scope

Implement the first read-only repo-forensics scanner: the Repo Cartographer.

This PR introduces a local command that loads `.gsd-forensics.yaml`, scans the repository filesystem, verifies configured entrypoints and critical modules exist, classifies high-level file groups, and writes a Markdown repo map report.

### Files Changed

- `tools/repo_forensics/__init__.py`
- `tools/repo_forensics/config_loader.py`
- `tools/repo_forensics/repo_cartographer.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_config_loader.py`
- `tests/test_repo_forensics_cartographer.py`
- `docs/agent_reviews/GSD_FOR_03_REPO_CARTOGRAPHER_SCANNER.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No merge automation.

### Expected Proof

- Config loader parses the strict YAML subset used by `.gsd-forensics.yaml`.
- Invalid/missing required config fails closed.
- Repo cartographer scans current checkout without importing runtime modules.
- Report writer emits scope guard, inventory, entrypoints, critical modules, and verdict.

## Approval Batching Model

This PR follows the reduced-friction model:

```text
many agents/checks internally
one local gate externally
```

The first gate command is:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

This command is read-only except for writing the Markdown report path requested by the operator.

## Grill Me Review

### Challenge

A scanner can create fake confidence if it claims runtime wiring proof from mere file existence.

### Findings

- Good: this PR only claims file/cartography proof.
- Good: the report explicitly says runtime wiring is not proven by this PR.
- Good: no target runtime modules are imported.
- Risk: current parser is a strict YAML subset, not a general YAML parser. That is acceptable because the config format is controlled.

### Verdict

PASS — useful as GSD-FOR-03 only. It must not be treated as runtime-wiring proof.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No runtime scripts modified.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The scanner uses only filesystem/static inspection and config parsing. It does not import `core.orchestrator`, `core.kite_client`, `strategies.trade_builder`, or dashboard runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Config loader added.
- [x] Cartographer added.
- [x] Report writer added.
- [x] Local runner added.
- [x] Tests added.
- [x] Evidence file added.
- [x] Next action is clear: GSD-FOR-04 Entrypoint and Runtime Wiring Audit.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Repo file inventory.
- Required/optional entrypoint existence check.
- Critical module existence check.
- Markdown repo map report.
- Local runner.
- Tests for config and current-checkout scan.

### Out of Scope

- Import graph.
- Runtime wiring proof.
- Test reality classifier.
- Safety boundary scanner.
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

PASS — narrow scanner implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR implements cartography only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover config parsing, invalid config, current checkout scanning, and report rendering.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

Full CI should run normally.

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-04 — Entrypoint and Runtime Wiring Audit

Expected next deliverables:

- static import/reference scanner
- run_live.sh -> main.py proof
- main.py -> safety/auth/readiness/orchestrator proof
- PASS/FAIL/UNKNOWN flow table
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
