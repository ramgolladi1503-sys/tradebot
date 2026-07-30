# TradeBot Enterprise QA Master Plan

Status: Phase 0 foundation

Base commit: `17262b4b6a42eb09d4d508bfdf6fe0d649ee32af`

## 1. Purpose

This program converts TradeBot from a repository with many tests into a system whose critical behaviors are explicitly specified, automatically verified, traceable, and release-gated.

The objective is not to manufacture a large test count. The objective is to prove that TradeBot:

- fails closed when live truth is missing or unsafe;
- never converts advisory or fallback evidence into executable permission;
- never emits duplicate or contradictory trade intent across retries or restarts;
- preserves data, decision, approval, execution, and reconciliation traceability;
- survives malformed input, delayed input, dependency failure, concurrency, restart, and sustained load;
- exposes enough evidence to explain every important decision and failure;
- keeps research, replay, paper, and live authority boundaries separate.

## 2. Blunt baseline assessment

TradeBot already has useful pytest infrastructure and many focused regression tests. It also defines markers such as `behavior`, `safety`, `regression`, `chaos`, `replay`, and `broker_firewall`.

That is a good start, but it is not yet an enterprise QA system because:

1. The existing structured catalog contains only 315 high-level cases and many generated tests are skipped skeletons.
2. CI runs one broad deterministic suite but does not currently enforce code coverage, branch coverage, mutation quality, dependency security, static security, or performance budgets.
3. Test count is not mapped to a complete module inventory and risk register.
4. Many tests protect individual bugs, but there is no repository-wide requirement-to-test traceability model.
5. Critical cross-module workflows are not governed by a single behavior contract and state-transition oracle.
6. A green suite can still hide weak assertions, excessive mocking, dead tests, untested branches, or tests coupled to implementation shape.

## 3. Coverage policy

A flat 100% repository-wide line-coverage gate is not the first milestone. Enforcing it immediately on a large existing repository would stop delivery and encourage meaningless assertions.

The required policy is risk weighted:

### Tier A — capital, credentials, live truth, or irreversible side effects

Examples: auth, feed freshness, contract resolution, execution gate, manual approval, order routing, risk limits, kill switch, reconciliation.

Required exit criteria:

- 100% line coverage;
- 100% branch coverage;
- all documented state transitions covered;
- mutation score at least 90% for deterministic business logic;
- zero surviving high-risk mutants;
- happy, negative, boundary, destructive, concurrency, restart, and observability contracts automated;
- broker firewall proves no unintended network or order path is reachable in offline tests.

### Tier B — decision quality and operational correctness

Examples: strategy orchestration, candidate pool, scoring, ranking, feature engineering, persistence, dashboard read models, reports.

Required exit criteria:

- at least 95% line coverage;
- at least 90% branch coverage;
- mutation score at least 80% for deterministic logic;
- replay parity and data-lineage contracts where applicable.

### Tier C — tooling, research utilities, one-off migration scripts

Required exit criteria:

- at least 85% line coverage;
- at least 80% branch coverage;
- critical parsing, destructive operations, and artifact-integrity paths covered.

Repository target after staged adoption:

- at least 95% line coverage;
- at least 90% branch coverage;
- 100% line and branch coverage for every Tier A module.

Coverage exclusions must be explicit, reviewed, and justified. Generated code, type-checking-only branches, and truly unreachable platform branches may be excluded. Business logic may not be excluded.

## 4. Test portfolio target

The expected automated portfolio is approximately 2,500 to 4,000 meaningful cases. This is a forecast, not a KPI.

| Test family | Expected cases | Purpose |
|---|---:|---|
| Module behavior contracts | 700–1,000 | Happy, negative, boundary, state, and invariants |
| Cross-module integration | 350–550 | Data and authority handoffs |
| Regression | 400–650 | Every escaped defect and high-risk fix |
| Property-based and metamorphic | 250–450 | Large input spaces and invariants |
| Chaos and destructive | 200–350 | Corruption, delay, dependency and restart failures |
| Replay and end-to-end | 180–300 | Production-like workflows without broker side effects |
| Security | 150–250 | Secrets, auth, injection, dependency and permission boundaries |
| Performance, load and soak | 100–200 | Throughput, latency, leaks, reconnect and persistence pressure |
| UI/read-model/accessibility | 100–180 | Truth display, filtering, stale state and operator workflows |
| Operational and recovery | 150–250 | Startup, shutdown, persistence, reconciliation and incident handling |

A test is counted only when it has an executable oracle. Skipped skeletons, `assert True`, duplicated parameter rows with no distinct behavior, and tests that only verify mocks were called do not count.

## 5. Seven-person QA operating model

### QA Lead / Technical Test Manager

Owns risk acceptance, test strategy, traceability, release gates, defect escape reviews, test-quality audits, and final certification.

### QA Engineer 1 — Authentication, security and configuration

Owns credential source precedence, token lifecycle, secret handling, startup validation, permissions, dependency security, and security regression.

### QA Engineer 2 — Market data, websocket and recovery

Owns tick/depth ingestion, ordering, deduplication, freshness, subscription truth, reconnect state machines, gaps, stale data, and feed soak.

### QA Engineer 3 — Strategy, features and market-event reasoning

Owns feature causality, completed-bar rules, regime behavior, candidate creation, scoring, ranking, strategy conflicts, replay/live parity, and future-leak prevention.

### QA Engineer 4 — Trade builder, contract resolution, risk and approval

Owns instrument resolution, quote authority, entry/SL/target construction, sizing, risk limits, manual approval, idempotency, and execution permission.

### QA Engineer 5 — Execution, persistence and reconciliation

Owns order intent, broker firewall, partial fills, retries, duplicate prevention, trade logs, restart recovery, SQLite integrity, reconciliation, and kill switch.

### QA Engineer 6 — Dashboard, observability, performance and CI

Owns read-model truth, UI status accuracy, logs/metrics/traces, report integrity, load/stress/soak tests, resource leaks, test infrastructure, CI/CD and quality reporting.

Cross-review rule: the engineer who writes a contract does not alone certify it. Every Tier A module requires a second QA engineer to review test design and mutation results.

## 6. Mandatory behavior model for every module

Every production module receives a Behavior Contract Sheet containing:

1. Purpose and authority boundary.
2. Inputs, outputs and side effects.
3. Preconditions and postconditions.
4. State model and legal transitions.
5. Invariants that must never be violated.
6. Happy paths.
7. Negative paths.
8. Exact boundary values.
9. Malformed and adversarial inputs.
10. Dependency failure and timeout behavior.
11. Retry, idempotency and duplicate behavior.
12. Concurrency and race behavior.
13. Restart and recovery behavior.
14. Security and data-classification behavior.
15. Observability requirements.
16. Performance budget.
17. Required test data and production-like fixtures.
18. Traceability IDs linking requirements, tests, defects and evidence.

A module is not certified because its lines executed. It is certified only when its behavior model is complete and the executable tests prove it.

## 7. Standard test design dimensions

Each behavior must be evaluated across relevant dimensions:

- functional correctness;
- positive and negative flows;
- boundary-value analysis;
- equivalence partitioning;
- decision tables;
- state-transition testing;
- pairwise/combinatorial configuration testing;
- property-based testing;
- metamorphic testing;
- model-based testing;
- fault injection and chaos;
- concurrency and race testing;
- restart, persistence and idempotency;
- security and abuse cases;
- performance, load, stress and soak;
- compatibility and configuration variation;
- observability and audit evidence;
- exploratory charters.

## 8. Two concrete behavior examples

### Example A — Auth token validation

Requirement: a valid canonical token permits client initialization; a missing, invalid, drifted, or unauthorized token must fail closed.

Representative automated cases:

- canonical runtime token file exists and is used even when an unrelated environment token is present;
- environment token is ignored unless the explicit CI-only override is enabled;
- missing required token raises the canonical auth failure;
- missing optional token returns empty without creating false success;
- credential drift after a client is initialized raises `CREDENTIAL_DRIFT_DETECTED` and does not create a second client;
- `TokenException`, HTTP 403, unauthorized, and invalid-session variants classify as auth failures;
- timeout and network failures classify separately from invalid-session failures;
- corrupted auth state returns an empty snapshot rather than crashing;
- `AUTH_REQUIRED` state is persisted with reason, source, code, timestamp and audit event;
- clearing auth creates explicit `OK` state and audit evidence;
- logs expose only approved token fingerprints, never complete secrets.

### Example B — Trade execution permission

Requirement: only a fresh, resolved, risk-approved, manually approved candidate may reach execution intent.

Representative automated cases:

- fresh live quote + valid contract + passing risk + valid approval permits exactly one intent;
- stale, REST fallback, reconstructed, missing, or mismatched quote remains advisory or blocked;
- duplicate approval callback does not create a duplicate intent;
- approval expires before execution and is rejected;
- risk state changes between approval and routing and revalidation blocks the order;
- contract changes after strategy emission and stale instrument identity is rejected;
- partial fill, retry, reconnect and process restart preserve idempotency;
- broker method is unreachable in PAPER and test modes;
- every result emits reason codes and trace IDs matching persisted state;
- forced persistence failure prevents execution rather than creating an unlogged order.

## 9. Test environments

### PR fast lane

- offline and deterministic;
- no broker, internet, Telegram, email or production secret access;
- unit, component, behavior, safety, regression, property and broker-firewall tests;
- target runtime under 15 minutes through sharding.

### Integration lane

- containerized temporary SQLite/filesystem services;
- deterministic fake broker and websocket servers;
- cross-module workflows and schema compatibility;
- target runtime under 30 minutes.

### Replay certification lane

- frozen market-data packs and immutable manifests;
- pipeline and decision replay;
- research/live causality and timing checks;
- scheduled nightly or manually dispatched.

### Security lane

- secret scanning;
- static security scanning;
- dependency vulnerability audit;
- malicious input and permission tests;
- scheduled and pull-request diff scanning.

### Performance lane

- feed burst, candidate-pool, persistence and dashboard-read load;
- reconnect soak and process resource tracking;
- nightly smoke and weekly certification.

### Controlled live-observation lane

- no automated order placement;
- manual approval preserved;
- production credentials never exposed to CI;
- captures evidence for feed, freshness, candidate flow and operational readiness.

## 10. CI/CD quality gates

The final pipeline will contain independent jobs so one green aggregate job cannot hide the failing quality dimension:

1. repository and test-governance validation;
2. Tier A safety contracts;
3. deterministic behavior and regression suites;
4. integration suite with fake dependencies;
5. line and branch coverage;
6. mutation testing on changed critical modules;
7. static analysis and type checking;
8. dependency and static security scanning;
9. secret scanning;
10. artifact/schema compatibility;
11. replay smoke;
12. performance-budget smoke;
13. test-result, coverage and evidence artifact upload.

Release branches additionally require replay certification, extended security, load/soak evidence, and manual release approval.

## 11. QA execution phases

### Phase 0 — Inventory and truth baseline

Deliverables:

- complete production-module inventory;
- current test-to-module map;
- skipped/xfail/weak-assertion inventory;
- current line and branch coverage baseline;
- test duration and flake baseline;
- risk tier and owner for every module;
- known-gap register.

Exit: no production module is unclassified.

### Phase 1 — Prove the pattern with auth

Deliverables:

- auth Behavior Contract Sheet;
- deterministic auth behavior, state, negative and destructive tests;
- secret/logging checks;
- auth module coverage and mutation report;
- identified production behavior gaps separated from passing regression coverage.

Exit: auth Tier A criteria pass or every failure is recorded as a blocking defect.

### Phase 2 — Critical execution spine

Scope:

`strategy output -> candidate -> trade builder -> contract resolver -> quote authority -> risk -> approval -> execution intent -> trade log -> reconciliation`

Exit: every illegal authority transition is proven impossible in offline automation.

### Phase 3 — Feed and market-data system

Scope: websocket lifecycle, subscriptions, freshness, gaps, ordering, dedupe, reconnect, fallback, startup and sustained pressure.

Exit: deterministic replay plus soak proves no false freshness, duplicate supply, reconnect storm, or silent starvation.

### Phase 4 — Strategy and decision system

Scope: features, causal sequencing, completed-bar rules, regimes, candidate pool, scoring, ranking, conflicts, timing and replay/live parity.

Exit: no future leak, no snapshot masquerading as sequence, and complete reason-code traceability.

### Phase 5 — Persistence, dashboard and operations

Scope: SQLite/file state, restart recovery, dashboard truth, reports, alerts, health gates, kill switch and runbooks.

Exit: displayed state and operational evidence agree with authoritative persisted state.

### Phase 6 — Non-functional certification

Scope: security, dependency risk, load, stress, endurance, fault injection, recovery, resource leak and compatibility.

Exit: agreed performance and security budgets pass with retained evidence.

### Phase 7 — CI/CD enforcement

Introduce gates progressively:

- report-only baseline;
- changed-code coverage gate;
- Tier A hard coverage gate;
- mutation gate;
- repository-wide threshold ratchet;
- release certification workflow.

Thresholds only increase. They never decrease to make a PR green.

## 12. Defect and regression policy

Every escaped defect must produce:

1. a minimal reproducer;
2. a failing regression test before the fix when practical;
3. the production fix in the owning module;
4. a negative-control test proving the test fails against the old behavior;
5. requirement and defect traceability;
6. an assessment of sibling modules with the same failure pattern.

Tests must not be made green through global monkeypatch shims that change runtime behavior during pytest. Temporary compatibility shims require an owner, removal issue and expiry date.

## 13. Test quality audit rules

The following are quality failures:

- `assert True` or assertions unrelated to the requirement;
- skipped generated skeletons treated as completed tests;
- testing only a mock call instead of the observable result;
- patching the function under test;
- broad exception assertions without checking the failure contract;
- tests depending on execution order or wall-clock time;
- live network calls in the deterministic suite;
- tests that modify production state outside temporary directories;
- coverage exclusions hiding business logic;
- duplicated cases that add count but no new behavior;
- xfails without owner, defect ID and expiry.

## 14. Required evidence dashboard

The QA dashboard will report by module and risk tier:

- total requirements and automated requirements;
- pass, fail, skip, xfail and flaky counts;
- line and branch coverage;
- mutation score;
- escaped defects and reopen rate;
- test duration and slowest cases;
- replay parity status;
- security findings by severity;
- performance-budget status;
- last certification commit and evidence hash.

## 15. Immediate implementation order

1. Add this master plan and initial module risk register.
2. Add the first auth behavior-contract suite.
3. Run the auth slice and full deterministic suite in an isolated worktree.
4. Measure current coverage rather than guessing.
5. Fix test defects before production defects.
6. Add coverage and test-governance CI in report-only mode.
7. Move to the trade-execution spine.

## 16. Definition of enterprise-ready QA

TradeBot is enterprise-QA ready only when:

- every production module is inventoried and risk classified;
- every Tier A behavior is traceable to executable automation;
- critical state machines have complete transition coverage;
- critical modules meet 100% line and branch coverage with strong mutation scores;
- cross-module authority and data-flow contracts pass;
- deterministic tests cannot reach broker/network/order side effects;
- security, performance, recovery and replay lanes produce retained evidence;
- CI gates cannot be bypassed by test count, skips, weak assertions or coverage exclusions;
- the release decision is reproducible from versioned evidence.
