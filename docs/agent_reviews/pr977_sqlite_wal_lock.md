# PR #977 — SQLite WAL lock contention scope and review

## Agent Work Contract

- `source_agent`: `gsd`
- `action`: `GENERATE_PATCH`, `UPDATE_DOCS`, `VERIFY_SCOPE`
- Title: Add a scoped MarketSessionStore WAL initialization fix for the captured completed-bar persistence lock.
- Requested and allowed code scope: `core/market_session_store.py`, `tests/core/test_market_session_store.py`; governance evidence paths are this review, the work item, the claim registry, and the verification matrix.
- Implementation: stop negotiating `PRAGMA journal_mode=WAL` on every connection; negotiate and verify WAL during initialization, preserving explicit failure, the existing `busy_timeout=30000`, and `synchronous=FULL`.
- Safety constraints: `read_only=true` for investigation; `is_order_action=false`; `broker_api_called=false`; `allowed_for_live_execution=false`; `append=false` for read-only evidence/contracts.
- No runtime, live, broker, order, credential, risk, feed, strategy, or configuration changes are in scope.

## Scope Guard

The underlying captured stack was reported at `MarketSessionStore.persist_completed_bar -> _conn -> PRAGMA journal_mode=WAL -> sqlite3.OperationalError: database is locked` in `live_observation.log:1030–1043`. The lock holder is unknown, and those lines have no embedded timestamp; their placement in the 15-minute live window is not independently established here. The change addresses repeated WAL mode negotiation as a plausible avoidable lock point. It does not establish that this was the initiating cause or that all SQLite contention is fixed.

The retry-after-lock assertion in `tests/core/test_market_session_store.py` is included in the pending PR branch update. A focused local rerun with that assertion present completed as 22 passed; this is local evidence and not hosted exact-head CI. No live process was inspected or altered by this governance task.

## Grill Me Review

Role-assigned reviewer: `/root/sqlite_grill_me` (agent identity unauthenticated). Review confirmed the narrow RCA boundary and advised against claiming the lock holder or universal contention cause without evidence. No broker, order, or runtime path was needed. This review is evidence of a role-assigned assessment, not authenticated human identity or a production finding.

## Hermes Review

Role-assigned architecture reviewer: `/root/sqlite_hermes` (agent identity unauthenticated). Review found initialization-time WAL verification consistent with the existing store boundary and fail-closed behavior. Concurrent first-time database initialization was not proven covered and remains a limitation; a WAL initialization error remains explicit.

## GSD Review

Role-assigned implementation review: `/root/sqlite_ba` and `/root/sqlite_qa` reported acceptance criteria and focused test coverage; `/root/sqlite_qa` identified no blocking scope issue. The implementation commit is `0714c423641f04cf6f987c95379af254c7fd9819`. The focused suite was reported as 22 passing tests on that implementation state. The additional retry-after-lock assertion now present as an uncommitted worktree edit was added after that run and is not covered by that result. Identity is not authenticated.

## QA / Safety Review

- Senior QA role: `/root/sqlite_senior_qa` reported no P1/P2 finding on the reviewed implementation and confirmed the stated test boundary (identity unauthenticated).
- UAT role: `/root/sqlite_uat` reported offline UAT pass for the scoped behavior; it did not exercise a live trading runtime, broker, or order path (identity unauthenticated).
- Business analysis role: `/root/sqlite_ba` recorded acceptance criteria including lock failure, explicit error propagation, and retry after release (identity unauthenticated).
- These role labels do not authenticate natural-person identities. No lifecycle or CI evidence establishes a live trading result.

## Acceptance Proof

- The implementation changes WAL negotiation/verification to initialization and keeps failure explicit; the implementation diff retains the existing busy timeout and full synchronous setting.
- Focused local rerun in the PR worktree with the retry-after-lock assertion present: `PYTHONPATH=. pytest -q tests/core/test_market_session_store.py --tb=short` — 22 passed. The run was observed during this turn. It is not hosted exact-head CI.
- The work item links the supplemental report through `evidence_refs`; its sealed G2 record remains an immutable record of the earlier run. The claim remains `UNVERIFIED` and exact-head hosted CI remains pending.
- The `tests/core/` material classification is added without changing the protected material prefix floor.
- This review does not imply that hosted checks have passed. Merge remains conditional on current exact-head required checks.

## Current PR / CI Status

At remote head `0714c423641f04cf6f987c95379af254c7fd9819`, GitHub reported failures for Trusted Base evidence coverage, `unit_tests`, and `agent-review-evidence`. The Trusted Base artifact identified two concrete coverage gaps: `core/market_session_store.py` lacked a current work-item record, and `tests/core/test_market_session_store.py` was unclassified. The PR worktree now contains the scoped work item, claim, verification-matrix classification, and review documentation intended to address those evidence-coverage gaps; this correction has not yet been published or checked by GitHub. The `unit_tests` failure was independently reproduced against unchanged `origin/main` candidate-feed registry inputs and is not caused by the SQLite patch. All three checks remain required; none is waived by this document.

## Runtime Proof Required After Merge

No runtime or live proof was performed or is claimed. Any later operational claim requires separately authorized, timestamped evidence identifying the exact deployed subject and relevant SQLite lock state. Do not restart the live run or alter a database as part of this PR.

## What This PR Does Not Prove

- The identity of the SQLite lock holder or the initiating cause of the captured lock.
- Elimination of all SQLite lock contention, or concurrent first-time initialization safety beyond tested cases.
- Exact-head hosted CI status, merge, deployment, production behavior, live readiness, or strategy performance.
- Any broker call, order action, risk-gate behavior, or market-data correctness.

## Human Approval

The user authorized scoped lifecycle work and requested that PR #977 be merged automatically once the required gates permit. This is not authorization to bypass checks, assert a passing check without exact-head evidence, alter runtime state, or claim live readiness. No independent authenticated human review is represented by this document.
