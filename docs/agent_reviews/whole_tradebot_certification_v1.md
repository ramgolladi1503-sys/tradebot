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

Mission: establish a fail-closed certification campaign for the complete authoritative TradeBot runtime. Authentication is one prerequisite, not the certificate.

Hard constraints:

- no live broker call or order placement;
- no strategy profitability or edge claim;
- no threshold reduction merely to obtain green CI;
- no skipped, fake, empty or test-shim-based proof;
- no `QA_CERTIFIED` verdict unless every mandatory gate passes on one immutable SHA;
- every failure must be classified as product defect, test defect, tooling defect, dependency defect or missing environment evidence.

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

- `.github/workflows/qa-whole-tradebot-certification.yml`
- `.github/workflows/qa-apply-whole-tradebot-repairs-v1.yml`
- `.github/workflows/qa-apply-whole-tradebot-repairs-v2.yml`
- `tools/qa_certification/__init__.py`
- `tools/qa_certification/whole_tradebot_manifest.py`
- `tools/qa_certification/evaluate_coverage.py`
- `scripts/apply_whole_tradebot_qa_repairs_v1.py`
- `tests/qa/test_whole_tradebot_coverage_evaluator.py`
- `tests/qa/test_whole_tradebot_cross_module_truth.py`
- `docs/agent_reviews/whole_tradebot_certification_v1.md`

The validated repair runner may add focused product fixes and negative security tests only after its focused test and Bandit checks pass.

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

The campaign does not modify strategy profitability assumptions, loosen execution gates, bypass human approval or introduce live behavior.

## Grill Me Review

### Weak assumptions challenged

1. **“Thousands of tests mean the whole bot is covered.”** False. The measured baseline is about 73% statement coverage and 61% branch coverage across the scanned packages. Fifty-six of 59 configured critical modules miss their assigned threshold.
2. **“Fallback is already advisory-only, so the UI issue is cosmetic.”** False. A cross-module test proved that `opportunity_engine` mutates a frozen `Trade` while applying the fallback firewall, causing `FrozenInstanceError` exactly when the engine should fail closed.
3. **“A separate secure dependency experiment makes the application secure.”** False. The default requirements path still resolves vulnerable Autobahn 19.11.2.
4. **“Bandit is noisy, so its findings can be ignored.”** False. The scan exposed unsafe archive extraction, untrusted XML parsing, unrestricted URL handling, permissive filesystem modes and predictable shared temporary paths.
5. **“A non-empty test marker proves a domain.”** False. The first inventory contained only one replay, one chaos and one UI-read-model test. Ownership depth must be strengthened.

### Failure modes

- fallback classification crashes and bypasses a clean advisory result;
- dashboard/operator pools misrepresent advisory rows as equivalent to executable opportunities;
- stale or fallback truth receives capital after a late-state mismatch;
- approval is reused after execution or a race;
- archive traversal writes outside the evidence directory;
- malicious XML expands external entities;
- network fetchers accept non-HTTP or local metadata URLs;
- database or fallback evidence is group/world accessible;
- dynamic SQL accepts an identifier that was not validated or quoted;
- a green deterministic suite hides untested restart, concurrency or reconciliation branches.

### Grill Me verdict

`BLOCK`

The complete runtime is not certified. The campaign and evidence gates are valid, but known defects and untested critical branches remain.

## Hermes Review

### Scope pass/fail

`PASS` for the QA campaign scope.

### Boundary violations found

- No live broker call or order action was introduced by this PR.
- One existing fallback-truth implementation violates immutable candidate ownership by mutating a frozen dataclass.
- The ordinary dependency install path violates the security boundary by retaining a vulnerable Autobahn version.
- Several input-handling modules do not yet fail closed against malicious archives, XML or URL schemes.

### Files not to touch check

Strategy thresholds, broker credentials, live configuration, order placement semantics and profitability logic remain outside this remediation batch.

### Hermes verdict

`PASS_WITH_BLOCKERS`

The work is correctly isolated, but merging is prohibited while certification gates remain red.

## GSD Review

### Delivery verdict

`PARTIAL_DELIVERY_NOT_CERTIFIED`

### Evidence summary

- Nine-area manifest resolves to real modules without duplicate targets.
- Full deterministic candidate run collected 6,869 tests; three failures were recorded: two manifestations of the frozen fallback defect and one replay-test serialization defect.
- Same-SHA 1,000-cycle feed/reconnect resource certification passed.
- Assurance-family inventory collected behavior, safety, edge, regression, replay, chaos, broker-firewall and UI-read-model tests, but several families remain thin.
- Per-module coverage gate failed 56 of 59 critical modules.
- Static security failed with 41 medium/high Bandit findings and one dependency vulnerability.
- Final certificate artifact correctly reported `NOT_CERTIFIED`.

### Next action

Repair the immutable fallback path and high-severity security boundaries, re-run focused proof, then use the coverage debt report to certify Tier-A areas one at a time without weakening thresholds.

## QA / Safety Review

### Test-quality review

- Generated skipped skeletons and unconditional `assert True` tests were previously removed from the executable suite.
- `sitecustomize.py` behavior patches were retired and the deterministic suite is exercised without automatic runtime rewriting.
- New cross-module tests use real immutable `Trade` objects, late-risk rejection, exactly-once approval consumption and canonical executable/advisory pools.
- New security controls require negative tests, not scanner suppression alone.

### Safety verdict

`FAIL_CLOSED_NOT_CERTIFIED`

No evidence permits live execution certification. Offline tests must never place an order. Controlled live observation remains a separate operator-approved evidence lane.

## Acceptance Proof

A valid whole-TradeBot certificate requires all of the following on the same commit:

1. manifest integrity passes;
2. full deterministic suite passes without `sitecustomize.py` behavior patches;
3. every Tier-A module has 100% line and branch coverage;
4. every Tier-B module has at least 95% line and 90% branch coverage;
5. required mutation thresholds pass with zero high-risk surviving mutants;
6. behavior, safety, edge, regression, replay, chaos, broker-firewall and UI-read-model portfolios meet reviewed ownership requirements;
7. cross-module fallback, ranking, late-risk, approval and operator-pool contracts pass;
8. same-SHA 1,000-cycle feed/reconnect certification passes;
9. static security and dependency audits contain no unresolved high/medium blocker;
10. restart, persistence, reconciliation and exactly-once evidence passes;
11. controlled-live observation proves feed and decision truth without unauthorized order placement;
12. independent human QA lead reviews and signs the evidence.

Current acceptance result: `FAIL`.

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
- safety of the current vulnerable default dependency graph;
- controlled-live certification.

## Human Approval

Human QA lead approval: **NOT GRANTED**.

Merge approval: **NOT GRANTED**.

Certification verdict: **NOT_CERTIFIED**.
