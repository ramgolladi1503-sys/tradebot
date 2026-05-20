# CE-05B — Code Excellence Agent Parameter Bridge

## Agent Work Contract

### Scope

Add a Code Excellence configuration bridge that loads and validates existing elite agent parameters from `.gsd-forensics.yaml`.

This prepares CE-06 and later implementation PRs to consume configured Ariadne, Daedalus, Vulcan, Minerva, and Cerberus parameters programmatically instead of hardcoding agent rules.

### Files Changed

- `tools/code_excellence/config.py`
- `tests/test_code_excellence_config.py`
- `docs/agent_reviews/CE_05B_AGENT_PARAMETER_BRIDGE.md`

### Hard Boundaries

- No product code changes.
- No remediation planner implementation.
- No scanner behavior changes.
- No trading logic changes.
- No broker behavior changes.
- No live runtime execution.
- No auto-fix.
- No auto-PR.
- No baseline debt cleanup.
- No test weakening.

## Deliverables

This PR adds:

- `AgentParameterProfile`
- `CodeExcellenceAgentParameters`
- `load_code_excellence_agent_parameters()`
- `extract_code_excellence_agent_parameters()`
- fail-closed validation for required CE agents and fields
- tests for loading, missing agent, missing field, empty list, and unknown agent access

## Gate 1 — Scope and Intent

PASS.

The scope is limited to loading existing CE agent parameters and validating them.

## Gate 2 — Truth and Root-Cause

PASS.

The root issue is that CE implementation PRs would otherwise hardcode agent behavior while `.gsd-forensics.yaml` already owns the elite parameters. This bridge fixes that design gap before CE-06.

## Gate 3 — Hardening and Proof

PASS pending CI.

Tests prove valid config loads and invalid config fails closed.

## Grill Me Review

### Challenge

A parameter bridge can become useless if it only loads raw dictionaries without enforcing required structure.

### Findings

- Good: required CE agents are explicit.
- Good: required fields are validated per agent.
- Good: list fields must be non-empty.
- Good: missing agent and unknown agent access fail closed.
- Risk: CE-06 must actually use this bridge; otherwise this is dead infrastructure.

### Verdict

PASS.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No planner implementation added.
- [x] No scanner behavior changed.
- [x] No broker behavior changed.
- [x] No live behavior changed.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Config bridge added.
- [x] Required CE agents validated.
- [x] Required fields validated.
- [x] Fail-closed tests added.
- [x] Agent evidence added.
- [x] Next action is clear: CE-06 should consume this bridge.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- CE agent parameter loading.
- CE agent parameter validation.
- Tests.
- Agent evidence file.

### Out of Scope

- Remediation planner.
- Ariadne clustering behavior changes.
- Product fixes.
- Runtime execution.
- Broker behavior.
- Live behavior.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_code_excellence_config.py
```

Required CI:

```text
repo-forensics-pr-gate
```

## Final Verdict

PASS pending CI.

## Next PR

CE-06 — Remediation Planner Implementation

Expected rule:

- CE-06 must use `load_code_excellence_agent_parameters()` instead of hardcoded Daedalus/Ariadne rules where config is needed.
