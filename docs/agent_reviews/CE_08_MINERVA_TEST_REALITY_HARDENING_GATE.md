# CE-08 — Minerva Test Reality Hardening Gate

## Purpose

Add a scoped Minerva gate for checking changed test files used as proof.

## Files Changed

- `tools/code_excellence/minerva_gate.py`
- `scripts/run_minerva_gate.py`
- `tests/test_code_excellence_minerva_gate.py`
- `docs/agent_reviews/CE_08_MINERVA_TEST_REALITY_HARDENING_GATE.md`

## Scope

In scope:

- static test-file review
- changed-path scoping
- configured Minerva parameters
- Markdown report generation
- deterministic tests

Out of scope:

- product code changes
- runtime execution
- code mutation
- auto-fix
- baseline cleanup

## Gate 1 — Scope and Intent

PASS.

## Gate 2 — Truth and Root-Cause

PASS.

The gate prevents weak changed tests from being treated as valid proof.

## Gate 3 — Hardening and Proof

PASS pending CI.

Targeted test:

```bash
PYTHONPATH=. pytest -q tests/test_code_excellence_minerva_gate.py
```

## Reviews

- Grill Me: PASS
- Hermes: PASS
- GSD: PASS pending CI
- Scope Guard: PASS

## Next PR

CE-09 — Cerberus Safety Regression Gate.
