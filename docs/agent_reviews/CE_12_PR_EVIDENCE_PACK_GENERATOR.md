# CE-12 — PR Evidence Pack Generator

## Purpose

Add a generator that creates a PR-ready evidence pack from the unified CE gate report.

## Files Changed

- `tools/code_excellence/pr_evidence_pack.py`
- `scripts/generate_pr_evidence_pack.py`
- `tests/test_code_excellence_pr_evidence_pack.py`
- `docs/agent_reviews/CE_12_PR_EVIDENCE_PACK_GENERATOR.md`

## Scope

In scope:

- consume unified CE gate output
- render a PR-ready body
- include changed files, gate status, blocked gates, tests, scope guard, and next step
- generate a standalone Markdown evidence pack
- deterministic tests

Out of scope:

- no GitHub posting
- no CI wiring
- no product behavior changes
- no runtime execution
- no code mutation
- no auto-fix
- no baseline cleanup

## Gate 1 — Scope and Intent

PASS.

## Gate 2 — Truth and Root-Cause

PASS.

The weak PR body problem after CE-07 needs a generated local evidence pack. This PR produces the text but does not post it automatically.

## Gate 3 — Hardening and Proof

PASS pending CI.

Targeted test:

```bash
PYTHONPATH=. pytest -q tests/test_code_excellence_pr_evidence_pack.py
```

## Reviews

- Grill Me: PASS
- Hermes: PASS
- GSD: PASS pending CI
- Scope Guard: PASS

## Next PR

CE-13 — CI Wiring for CE Gates.
