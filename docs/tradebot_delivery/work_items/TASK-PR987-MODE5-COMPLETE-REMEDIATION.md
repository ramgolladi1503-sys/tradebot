# TASK-PR987-MODE5-COMPLETE-REMEDIATION

**State:** DEV_PARTIAL / HOLD

**Type:** TASK

**Parent:** `EPIC-SENTINEL-REGIME-SUPERVISORY` / `FEAT-SENTINEL-STRUCTURAL-GATES-002`

**Candidate base:** `c9608df0830ef9331fec1c467edd8fa5dc163d6d`

## Goal

Correct and verify bounded Sentinel Mode 5 bar, chronology, replay, OR state, and quote-ordering defects in an isolated candidate. No PR merge, execution activation, broker action, or deployment is authorized.

## Acceptance status

- Synthetic tick buckets without completeness proof do not become strategy bars or candidates: **implemented, focused evidence recorded**.
- OR snapshot application is session/generation/request fenced; target/companion evidence is atomic and diagnostic-only in the research profile: **implemented, focused evidence recorded**.
- Replay uses explicit event-clock validation and fails closed when monotonic capture provenance cannot be mapped: **implemented, focused evidence recorded**.
- Quote ordering/freshness is rechecked before APM evaluation: **implemented, focused evidence recorded**.
- Mode 5 stops before sizing/dispatcher/APM entry without an approved sizing contract: **implemented, fail-closed**.
- Exact four-module run: **286 passed, 1 environment-blocked, 0 skipped**. The block is Python 3.14 multiprocessing `SemLock` creation denied by the sandbox before product code.
- `py_compile` and `git diff --check`: **PASS**.
- QA and Technical & Quant: **HOLD**; Senior QA: **BLOCK** for acceptance/readiness; UAT re-review required after report cleanup; Release Manager: **PASS for review-only draft push**.
- CodeRabbit: **7 core + 5 test findings remain open**.

## Current source hashes

- Advisor: `510766566f00a42a6f4707d0cccb6b33676c9dbe6bfefd38d03eb9a81bfccfe7`
- Hardening tests: `e9069597d71f5ef2c51af57435f047fe71e06cd77c00de93bc6a0720e82cfcdd`
- Execution tests: `ad033a3d9dced9c43f09bfacede021c354c237fecf5be5f6b473db4748df7c65`
- OR policy tests: `6c9eed225a24a8f2e00555a3beecec6c2b44b507bd08e92364ebd4475ff7696d`
- Replay reproduction tests: `7944ad5c98340564c5c6cbd3cb91d637c114caa520946f91cc788d32022de22d`

See `docs/agent_reviews/PR987_MODE5_COMPLETE_REMEDIATION_REPORT.md` and `docs/agent_reviews/PR987_MODE5_COMPLETE_REMEDIATION_EVIDENCE.json` for the exact invocation, current inventory, review findings, and unresolved gates.

## Unresolved blockers

- No authoritative completed-bar/finality/continuity source is wired into the live advisor.
- No approved sizing policy exists; Mode 5 remains non-authorizing.
- EOD position management may be skipped on stale spot or one-sided option depth; no fallback exit-price policy is approved.
- Journal failure may prevent exit dispatch; no exit-ordering change is approved.
- CodeRabbit source and test findings remain open; broader parity, historical execution evidence, and full CI are incomplete.
- External task intake remains `UNSATISFIED`.

## Scope and safety

Include only the advisor, the four listed unit test files, this work item, the evidence JSON, and the remediation report. Exclude `.qa-sandbox/`, runtime/WAL/lock/trace/OR-ledger files, credentials, and unrelated research. The Mode 5 research profile changes candidate eligibility and target scaling; it is not behavior-neutral, is not approved for activation, and establishes no profitable edge. Keep PR #987 Draft/HOLD.
