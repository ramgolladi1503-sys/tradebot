# Enterprise QA Foundation V1 — Agent Review Evidence

## Agent Work Contract

Objective: establish the first auditable slice of a repository-wide QA certification program without changing production runtime behavior.

Allowed scope:

- QA strategy and certification documentation;
- module risk classification and ownership;
- deterministic authentication behavior tests;
- evidence required to explain what has and has not been proven.

Forbidden scope:

- changing authentication runtime behavior to satisfy tests;
- weakening safety assertions;
- enabling broker access in CI;
- claiming repository-wide certification from this foundation PR;
- merging the PR without human review.

## Scope Guard

Changed files are limited to QA documentation, this review evidence, and authentication tests. No production module, configuration, broker, feed, execution, risk, strategy, dashboard, persistence, or reconciliation implementation is modified.

The tests must exercise public or operationally meaningful behavior. Tests that only import a module, assert a mock call with no state/output invariant, or use unconditional assertions are not accepted as certification evidence.

## Grill Me Review

Questions used to challenge the work:

1. Does a large test count prove safety? No. Duplicate parameter cases, skipped skeletons, weak mocks, and line-only execution can inflate counts without detecting behavioral defects.
2. Does a green full pytest run prove live correctness? No. Network, broker, market-session, load, timing, restart, and controlled-live behavior require separate evidence lanes.
3. Can 100% line coverage prove branch safety? No. Critical allow/block branches and fail-closed transitions must each be asserted and mutation-tested.
4. Could these tests pass while the token is invalid in the real broker? Yes. The suite uses deterministic fakes and proves local contracts, not current broker validity.
5. Could test-only shims hide production defects? Yes. Existing compatibility/shim mechanisms remain explicit QA debt and must be removed or independently bounded before final certification.

Verdict: limited foundation acceptance only. The additions are suitable to begin the certification program, but they do not certify TradeBot as a whole.

## Hermes Review

Traceability review:

- Enterprise QA principles are documented in `docs/qa/ENTERPRISE_QA_MASTER_PLAN.md`.
- Initial risk ownership is documented in `docs/qa/MODULE_RISK_REGISTER.md`.
- Authentication behavior evidence is implemented in `tests/auth/test_auth_manager_behavior_contracts.py`.
- The tests trace to token source precedence, missing credential behavior, auth error classification, profile validation outcomes, persistent auth state, corrupt-state handling, audit events, and secret redaction.

Evidence gaps are not hidden: repository-wide coverage, mutation score, performance budgets, security scans, integration environments, replay/live parity, and controlled-live proof remain future certification work.

## GSD Review

Delivery review:

- The PR is isolated and draft.
- Production runtime code is untouched.
- The deterministic CI workflow passed on the initial head.
- CodeQL, Portfolio CI, Repo Forensics, Strategy Registry, and Code Excellence passed on the initial head.
- The Agent Review Evidence Gate failed because this mandatory document was absent; this file corrects that process defect.
- The broader `tests` workflow was still running when the initial evidence was inspected and must be checked again on the new head.

No failed assertion has been waived. Any later test failure must be diagnosed as either a test defect, environment defect, or product contract defect with evidence.

## QA / Safety Review

Safety invariants for this PR:

- no test may contact Zerodha or any broker endpoint;
- no environment token is accepted unless the explicit CI allow flag is enabled;
- canonical file-token precedence is asserted;
- missing mandatory credentials fail;
- authentication errors invalidate cached trust;
- network ambiguity remains distinct from verified authentication;
- persisted authentication state tolerates malformed files without crashing;
- logs may expose only credential fingerprints/tails, never full secrets.

A critical finding remains recorded for subsequent hardening: `validate_token()` can currently return `ok=True` with `auth_state="UNKNOWN_NETWORK"`. Consumers must not treat the boolean alone as proof of authenticated readiness. This PR tests and documents that current contract; it does not silently change it.

## Acceptance Proof

Acceptance evidence required for this PR:

1. `pytest -q tests/auth/test_auth_manager_behavior_contracts.py`
2. full deterministic pytest lane in paper/offline mode;
3. mandatory repository PR gates green;
4. no production runtime files changed;
5. review evidence validator green;
6. no secrets present in committed tests or logs.

At the time this document is added, prior-head evidence shows `ci`, CodeQL, Portfolio CI, Repo Forensics, Strategy Registry, and Code Excellence succeeded. All checks must be re-evaluated against the new commit before acceptance.

## Runtime Proof Required After Merge

This PR should not be merged solely because deterministic tests pass. Before final TradeBot QA certification, separate evidence is required for:

- real token expiry and refresh lifecycle in a controlled non-trading session;
- broker-profile timeout and invalid-session differentiation;
- websocket auth failure propagation into feed and candidate readiness;
- no order placement while auth is unverified;
- restart recovery from persisted `AUTH_REQUIRED` state;
- log inspection proving full credentials are absent;
- extended feed and execution safety soak tests.

These are certification-program requirements, not proof supplied by this documentation-and-test-only PR.

## What This PR Does Not Prove

This PR does not prove:

- repository-wide QA certification;
- trading profitability or strategy edge;
- correct live broker behavior;
- full code or branch coverage;
- mutation-test strength;
- absence of security vulnerabilities;
- performance, load, stress, endurance, or penetration readiness;
- replay/live parity;
- execution exactly-once behavior;
- reconciliation correctness;
- dashboard truth;
- that all existing tests are strong or free from compatibility-shim influence.

## Human Approval

Human approval is required before merge. The reviewer must confirm that the limited scope and non-claims are understood, that no production behavior changed, and that all checks on the final head are green. Approval of this PR is approval to continue the QA certification program, not certification of the entire TradeBot.
