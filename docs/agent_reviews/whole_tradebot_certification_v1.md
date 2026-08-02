---
title: Whole-TradeBot QA Certification V1
review_type: independent_qa_safety_review
status: NOT_CERTIFIED
branch: qa/whole-tradebot-certification-v1
pull_request: 762
scope: complete_authoritative_tradebot_runtime
runtime_change_authority: no_live_orders
---

# Whole-TradeBot QA Certification V1 — Independent Review Record

## Agent Work Contract

Mission: establish a fail-closed certification campaign for the complete authoritative TradeBot runtime. Authentication is one prerequisite, not the project certificate.

Hard constraints:

- no live broker call or order placement;
- no strategy profitability or edge claim;
- no threshold reduction merely to obtain green CI;
- no skipped, fake, empty or test-shim-based proof;
- no `QA_CERTIFIED` verdict unless every mandatory gate passes on one immutable SHA;
- every failure is classified as product, test, tooling, dependency, repository or environment evidence debt.

## Purpose

Convert the repository from “many tests” into a system whose startup, feed, decision, ranking, trade construction, risk, approval, execution, persistence, reconciliation and operator truth are independently release-gated.

## Scope

The certification manifest covers nine system areas:

1. runtime startup and authentication;
2. feed/WebSocket lifecycle and market-data truth;
3. orchestration and decision flow;
4. trade builder and instrument resolution;
5. risk, manual approval, review queue and execution boundary;
6. persistence, reconciliation and recovery;
7. candidate scoring, ranking and capital selection;
8. dashboard, observability and operator truth;
9. feature, strategy, replay and ML truth.

Research-only utilities remain outside the production certificate unless they are authoritative in a live, paper or replay decision path.

## Files Changed

The current PR includes certification workflows, coverage and mutation tooling, focused high-risk tests, secure dependency installation, input-boundary hardening, ranking/UI contracts and supporting review evidence. The authoritative changed-file list remains the Git diff against `agent/enterprise-qa-foundation-v1`.

## Scope Guard

Protected boundaries:

- broker and order APIs;
- manual approval and exactly-once consumption;
- live/paper/replay authority separation;
- feed freshness and fallback execution firewall;
- strategy logic and thresholds;
- risk limits and kill-switch behavior;
- evidence persistence and reconciliation;
- dashboard read-model truth.

The campaign does not modify strategy profitability assumptions, loosen execution gates, bypass human approval or introduce live order behavior.

## High-Risk Path Review

### Authentication authority

`core/auth.py` and `core/auth_manager.py` remain fail closed. Missing API key, missing token, credential drift, invalid profile state and broker-client absence return explicit failure states or raise explicit errors. Network uncertainty is represented as `UNKNOWN_NETWORK` with `ok=False`; it is never treated as authenticated.

Feed-startup telemetry is loaded lazily so credential tests do not import the feed runtime. The public telemetry patch point remains available for existing contracts. The lazy wrapper and its private compatibility delegate are included in the 100% line/branch coverage lane.

The auth mutation lane now runs an isolated contract suite rather than importing the broker/feed runtime. It has progressed from setup failure to real mutant execution. The first completed run produced 415 surviving mutants; exact behavioral contracts reduced this to 255. Logging and redaction-only expressions are excluded with explicit Mutmut pragmas, while credential authority, state transitions, return payloads, broker construction and ticker lifecycle remain mutation-active. The mutation gate remains red until meaningful survivors are eliminated or individually justified as equivalent behavior.

### Dependency and broker SDK supply chain

The ordinary requirements file no longer directly resolves KiteConnect or Autobahn. `scripts/install_tradebot_dependencies.py` is the canonical path: it removes any existing broker SDK graph, installs base requirements, verifies the official KiteConnect 5.2.0 wheel hash, builds the provenance-bearing `5.2.0+tradebot.1` wheel with a secure Autobahn constraint, installs it and runs `pip check`.

The verified path is wired into ordinary CI, the test workflow, unpatched owner truth, whole-system certification and Docker builds. Dependency certification audits the installed environment, including the patched broker SDK, rather than auditing only a requirements file that intentionally excludes the broker package.

### Execution, risk and state safety

No live order call was introduced. Candidate fallback truth is evaluated without mutating immutable inputs. Focused tests cover runtime boot-safety mapping and environment branches, disabled/unknown decision-breaker states, corrupt risk-halt state and persistence of a halt when incident notification fails.

The same-SHA 1,000-cycle feed/reconnect certification remains required. Manual approval, late-risk revalidation, fallback exclusion from executable pools and exactly-once approval consumption remain mandatory cross-module contracts.

### Input and SQL boundaries

Dynamic SQLite table selection in feed self-test code was replaced with a literal approved-query registry. Unknown or malicious identifiers fail closed, and injection-shaped values are covered by negative tests. Remaining scanner findings are reviewed individually; repository-wide suppression is prohibited.

### Current high-risk conclusion

The high-risk changes are correctly isolated and tested more deeply than the prior baseline, but whole-system certification is not granted. Remaining red gates include mutation survivors, repository-forensics debt, critical-module coverage debt, malformed Git LFS state, security findings outside the repaired slice and controlled-live evidence.

## Grill Me Review

### Weak assumptions challenged

1. **“Thousands of tests mean the whole bot is covered.”** False. Most configured critical modules remain below their assigned line/branch thresholds.
2. **“Fallback is already advisory-only, so the UI issue is cosmetic.”** False. Cross-module truth must prove fallback rows cannot obtain execution authority, capital or primary operator-pool visibility.
3. **“A separate secure dependency experiment makes the application secure.”** False. Security is credible only when every normal install path uses the verified broker graph.
4. **“Bandit is noisy, so its findings can be ignored.”** False. Dynamic SQL, archive, XML, URL, filesystem and broker-boundary findings require code proof or narrow evidence-backed classification.
5. **“High coverage proves strong tests.”** False. Mutation testing exposed hundreds of changes that the previous auth assertions did not detect.

### Failure modes under review

- fallback classification crashes or leaks execution authority;
- dashboard pools misrepresent advisory rows as executable opportunities;
- stale or fallback truth receives capital after a late-state mismatch;
- approval is reused after execution or a race;
- credential uncertainty is mislabeled authenticated;
- dependency installation silently restores a vulnerable broker graph;
- dynamic SQL accepts an unapproved identifier;
- a green deterministic suite hides restart, concurrency or reconciliation branches.

### Grill Me result

`BLOCK`

The complete runtime is not certified. The campaign and evidence gates are valid, but the remaining red gates prohibit a release certificate.

## Hermes Review

### Scope pass/fail

`PASS` for the QA campaign scope.

### Boundary review

- No live broker call or order action was introduced.
- Secure dependency installation is now a canonical path rather than a special experiment.
- Authentication telemetry imports were decoupled without changing credential authority.
- Strategy thresholds, broker credentials, order placement semantics and profitability logic remain outside this remediation batch.

### Hermes result

`PASS_WITH_REMAINING_GATES`

The work is correctly isolated, but merging remains prohibited while certification prerequisites are red.

## GSD Review

### Delivery status

`PARTIAL_DELIVERY_NOT_CERTIFIED`

### Evidence summary

- The nine-area manifest resolves to real modules without duplicate targets.
- The deterministic suite previously reached 6,877 passing tests with two stale input-mutation expectations; those tests were corrected to assert pure fail-closed behavior.
- Same-SHA 1,000-cycle feed/reconnect resource certification has passed on prior candidates and remains a mandatory lane on the final SHA.
- Test-integrity and runtime-shim gates are green on recent candidates.
- Auth line/branch coverage remains fixed at a 100% threshold; the lazy telemetry test has been added to the workflow after a 99.13% run exposed the omission.
- Mutation execution is functioning and has produced real survivor evidence.
- The final certificate artifact remains `NOT_CERTIFIED` while any prerequisite is red.

### Next action

Re-run the corrected auth coverage and mutation lanes, clear truthful repository-forensics classifications, then use the coverage debt report to certify Tier-A areas one at a time without weakening thresholds.

## QA / Safety Review

### Test-quality review

- Generated skipped skeletons and unconditional `assert True` tests were removed from the executable suite.
- `sitecustomize.py` behavior patches were retired and the deterministic suite is exercised without automatic runtime rewriting.
- Cross-module tests use immutable candidates, late-risk rejection, exactly-once approval consumption and canonical executable/advisory pools.
- Security controls require negative tests, not scanner suppression alone.
- Mutation exclusions are limited to observability-only expressions and use explicit source markers.

### Safety status

`FAIL_CLOSED_NOT_CERTIFIED`

No evidence permits live execution certification. Offline tests must never place an order. Controlled live observation remains a separate operator-approved evidence lane.

## Acceptance Proof

A valid whole-TradeBot certificate requires all of the following on the same commit:

1. manifest integrity passes;
2. full deterministic suite passes without `sitecustomize.py` behavior patches;
3. every Tier-A module has 100% line and branch coverage;
4. every Tier-B module has at least 95% line and 90% branch coverage;
5. required mutation thresholds pass with no high-risk surviving mutants;
6. behavior, safety, edge, regression, replay, chaos, broker-firewall and UI-read-model portfolios meet reviewed ownership requirements;
7. cross-module fallback, ranking, late-risk, approval and operator-pool contracts pass;
8. same-SHA 1,000-cycle feed/reconnect certification passes;
9. static security and dependency audits contain no unresolved medium/high release issue;
10. restart, persistence, reconciliation and exactly-once evidence passes;
11. controlled-live observation proves feed and decision truth without unauthorized order placement;
12. independent human QA lead reviews and signs the evidence.

Current acceptance result: `NOT_CERTIFIED`.

## Runtime Proof Required After Merge

This draft must not be merged as a certificate. After offline gates clear, an operator-approved observation must capture:

- authenticated startup and fail-closed recovery;
- physical feed connection and freshness;
- candidate generation through canonical ranking pools;
- fallback rows remaining advisory-only;
- late risk and approval revalidation;
- persistence and reconciliation across restart;
- zero broker order calls unless the operator separately approves a controlled action.

## What This PR Does Not Prove

- profitable strategy edge;
- production readiness;
- live broker compatibility under every market condition;
- zero operational incidents;
- correctness of unmeasured branches;
- controlled-live certification;
- human release approval.

## Human Approval

Human QA lead approval: **NOT GRANTED**.

Merge approval: **NOT GRANTED**.

Certification status: **NOT_CERTIFIED**.
