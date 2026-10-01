# Adversarial PR Gate V1 Review

## Agent Work Contract

source_agent: ChatGPT
action: GENERATE_PATCH / CREATE_ACCEPTANCE_GATES
title: Adversarial PR Gate V1
scope: repository-level fail-closed PR attack gate
requested_paths: `.github/workflows/adversarial-pr-gate.yml`, `scripts/run_adversarial_pr_gate.py`, `tests/governance/test_adversarial_pr_gate.py`
allowed_paths: requested paths plus this review document
forbidden_paths: broker/order/risk/live runtime/strategies/credentials
expected_tests: governance self-tests and ordinary repository CI
acceptance_proof: exact-head workflow success plus adversarial gate self-tests

## Scope Guard

This PR adds governance only. It does not change any trading strategy, threshold, broker adapter, execution engine, order path, risk engine, live feed, credential, or LIVE/PAPER/SIM behavior.

## Grill Me Review

Questions attacked:

- Can a PR omit tests after production-code changes? Gate fails.
- Can a PR add only happy-path tests? Gate fails unless at least one explicitly adversarial/negative/safety/mutation/attack test changes too.
- Can a PR weaken tests by adding skip/xfail markers? Gate fails.
- Can a PR delete assertions without replacing equivalent assertions? Gate fails.
- Can a PR add `eval`, `exec`, `compile`, or `__import__` calls in production Python? Gate fails.
- Can a PR break Python syntax? Gate fails.
- Can a PR modify the adversarial gate itself? Gate fails outside the dedicated governed bootstrap/recertification branch.
- Can a PR bypass trusted policy by editing candidate code? The trusted `pull_request_target` job runs only the protected-main copy of the gate and does not execute candidate code.
- Can the candidate execution job use secrets? Workflow grants only `contents: read`, uses `persist-credentials: false`, and does not request secrets.

Known limitations are documented below rather than hidden.

## Hermes Review

Architecture uses two trust domains:

1. `pull_request` candidate execution job: untrusted candidate checkout, no secrets, changed adversarial tests executed.
2. `pull_request_target` trusted policy job: protected-main checkout, exact candidate fetched as data only, candidate code never executed.

This separation prevents a candidate from weakening its own gate and then relying on the weakened implementation for trusted policy approval.

## GSD Review

Implementation is bounded to one workflow, one gate runner, one governance test file, and this review document. No runtime wiring is introduced.

## QA / Safety Review

Negative cases cover high-risk classification, production-without-test, production-without-adversarial-test, gate self-modification, syntax corruption, newly-added dangerous dynamic execution APIs, added skip markers, assertion deletion, and docs-only changes.

Safety invariants:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```

## High-Risk Path Review

No trading high-risk path is changed. The governance workflow itself is treated as high-risk governance surface and is self-protected after bootstrap.

## Acceptance Proof

Required before merge:

- `tests/governance/test_adversarial_pr_gate.py` passes on exact head.
- candidate adversarial execution job passes on exact head.
- trusted adversarial policy job passes or bootstrap exception is explicitly understood.
- existing agent-review, repo-forensics, CodeQL, and CI gates do not regress.
- PR remains draft if any of the above is unresolved.

## Runtime Proof Required After Merge

After merge, open a harmless proof PR that changes a tiny production helper plus only a happy-path test. The new gate must fail it for missing adversarial test evidence. Then add a negative/adversarial test and confirm the gate passes. This is required to prove the protected-main `pull_request_target` half is actually active.

## What This PR Does Not Prove

It does not prove that every possible bug class is automatically discoverable. File-name-based adversarial-test classification can prove the presence of an explicitly named adversarial test file, not the semantic quality of every assertion. It also does not replace full CI, CodeQL, domain-specific mutation campaigns, source/spec conformance review, load/soak tests, or human review.

The gate is intended as a mandatory minimum attack floor, not a claim of exhaustive formal verification.

## Human Approval

Human approval is still required for merge. A green adversarial gate is evidence that the minimum attack contract was satisfied; it is not execution authority or permission to bypass repository governance.
