# Continue LOOP-EXAMPLE

Read root `AGENTS.md` first. GitHub is authoritative; local-only work is not proof.

## Objective
Prove that a new worker can resume a bounded non-runtime task from committed GitHub evidence alone.

## Current state
- State: `REVIEWING`
- Code SHA: `17262b4b6a42eb09d4d508bfdf6fe0d649ee32af`
- Branch: `infra/github-first-loop-engineering-v1`
- Completed gate: `example_test_proven`
- Blockers: none

## Next action
Review `CLM-EXAMPLE-1` against `TEST-EXAMPLE-1`. Record an independent review proof only when the committed evidence is sufficient. Do not modify runtime code.

## Scope
Allowed: `docs/example/**`

Forbidden: `main.py`, `run_live.sh`, `config/**`, `core/**`, `strategies/**`, credentials, and environment files.

## Required evidence
- `claims.json`
- `evidence/manifest.json`
- `evidence/example_test_summary.txt`
- branch and GitHub Actions status

## Optional backlog
An external agent dispatcher may be considered later. It is not part of this task.

Perform only this review transition, checkpoint before stopping, and do not merge.
