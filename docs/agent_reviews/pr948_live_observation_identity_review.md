# PR948 live observation identity review

## Agent Work Contract

`source_agent: hermes + gsd`; actions: `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`. Scope is the MEG cash-observation identity boundary in the direct and installed subscription builders. No broker/order calls, live process operations, credentials, or production-data mutation are permitted.

## Scope Guard

Only `core/depth_subscription_engine.py`, `core/kite_depth_ws.py`, focused tests, and these review/contract artifacts are in scope. In MEG mode, only configured index products reach option resolution. Verified cash observation tokens are added to the underlying identity maps after a successful merge. The 123-token budget/topology, feed freshness, recovery behavior, option-health evidence, risk gates, kill switches, and execution authority are unchanged. No new config key or migration is introduced.

## Grill Me Review

The stale PR branch includes superseded token-budget and feed-evidence edits. Those must not survive reconciliation with current main. Merging stale code wholesale could restore the 150-token fallback or weaken the newer WebSocket recovery and option-health evidence behavior. Review the final diff against current main; do not infer correctness from the old PR checks.

## Hermes Review

The governing design is `docs/contracts/pr948_hermes_cash_observation_contract.md`. It separates option product symbols from cash observations and requires exact registry identity after successful union construction.

## GSD Review

Execution steps and acceptance cases are defined in `artifacts/issues_7_11/GSD_PR948_OBSERVATION_IDENTITY_PLAN.md`. Tests must cover both builders, resolver input symbols, exact union size, successful identity publication, and blocked-merge non-publication.

## QA / Safety Review

Validation is offline and deterministic. It must not call a broker or live process. The blocked-merge case must remain fail-closed. PR782/PR818 checks are excluded as directed; their failures are not treated as passing evidence.

## Acceptance Proof

The final candidate diff against current `main` contains only the two subscription builders, focused tests, and this PR's review/contract artifacts. The stale PR's budget, recovery, health-evidence, and runner changes are not in the candidate diff. The focused offline suite passed: `pytest -q tests/test_depth_subscription_tokens.py tests/test_depth_subscription_refresh_contract.py tests/test_subscription_universe_123_contract.py tests/test_kite_depth_ws_stability.py` — **90 passed**. `git diff --check` passed. Exact-head hosted CI remains pending. PR782 and PR818 are excluded by user instruction and are not represented as passing evidence.

## High-Risk Path Review

`core/depth_subscription_engine.py` and `core/kite_depth_ws.py` are high-risk feed paths. The patch filters MEG option-resolution inputs to `NIFTY`, `BANKNIFTY`, and `SENSEX`; cash-only inputs raise a clear error instead of creating an observation-only ready state. It requires complete registry-token identity coverage and final-union membership before publishing identities into generic and underlying maps. Conflicting or incomplete identity blocks readiness, and failed merges publish no observation-only identities. Tests confirm the 123-token union and resolver inputs. Budget, option selection/counts, recovery logic, freshness gates, and execution controls are unchanged by this scoped patch. No live process or broker was used.

## Runtime Proof Required After Merge

Separately authorized read-only observation must compare the active subscription identities and token-to-symbol maps to the canonical registry. Offline tests and CI do not prove live delivery, freshness, recovery, or live readiness.

## What This PR Does Not Prove

It does not prove that the upstream registry is current, that every provider tick arrives, that the live observation session is healthy, or that any trading candidate is safe or authorized for execution.

## Human Approval

No approval for live runtime operations or execution is represented here. The PR remains subject to human review; no live run is authorized by this contract.
