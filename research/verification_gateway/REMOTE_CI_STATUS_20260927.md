# PR #936 remote CI result — 2026-09-27

- PR: https://github.com/ramgolladi1503-sys/tradebot/pull/936
- Latest tested commit: `32b26a1e582a098486abbf3642323d310b16218c`
- Latest focused workflow: `candidate_ml_v2`, run `36313532028`.
- Focused `candidate_ml_v2` tests: **PASS**.
- Replay-ledger proxy training lane: **PASS**; this is not real-market evidence or strategy certification.
- Real-market corpus pilot: **FAIL before setup/training** at `Materialize selected historical corpus`. Git LFS returned: `This repository exceeded its LFS budget`. No selected corpus files were materialized, validated, or trained on. This is an external repository/account dependency; do not retry until LFS access is restored or an authorized equivalent source is supplied.
- At the 2026-09-27T10:46:43Z snapshot, `unit_tests` remained pending and `verify` passed. `code-excellence-base-authority`, `pr818-live-flow-freeze-target`, and Netlify deploy-preview checks were failing. Passing analysis, security, synthetic gateway, candidate, docs and code-excellence gate checks do not supersede these failures.
- PR #936 remained draft and `BLOCKED` at this snapshot. No CI workflow or root dependency manifest was changed.
- No protected outcome content was read locally; GitHub's failed LFS fetch attempted only the explicitly selected object paths in the CI job, and returned no objects. The training step was skipped.

Recheck exact-SHA status with:

```sh
gh pr checks 936
gh run view 36313532028 --json jobs
```
