# Tradebot QA Gate

## Purpose

The QA Gate prevents Tradebot PRs from merging without behavior proof, edge proof, and safety proof.

The gate exists because a trading product can pass many small tests and still fail the product truth:

> It can show candidates that are not executable, rank weak opportunities as strong, or report fake profitability.

## Required PR Evidence

Every production-code PR must include:

1. Intended behavior summary.
2. Edge purpose.
3. Positive behavior test.
4. Negative/fail-closed behavior test.
5. Regression test if the PR fixes a bug.
6. Focused test command.
7. Relevant regression command.
8. Safety proof if the PR touches feed, broker, execution, dashboard, replay, runtime, scoring, ranking, or candidate flow.

## QA Gate Questions

A PR passes only when all applicable answers are yes:

- Does the PR include tests?
- Do the tests prove intended behavior rather than current code behavior?
- Does every test protect, prove, measure, or improve trading edge?
- Is at least one unsafe or negative path tested?
- Does the PR preserve broker/network/order safety?
- If dashboard or replay is touched, is the path still read-only?
- If feed is touched, does stale/missing/fallback proof fail closed?
- If ranking is touched, is score separation or safety ordering proven?
- If candidate flow is touched, are blocked/advisory/executable buckets proven?
- If a bug is fixed, is there a regression test that would fail on the old bug?

## QA Gate Outcomes

### PASS

All required evidence exists and focused tests pass.

### BLOCKED

Any required behavior, edge, negative, safety, or regression evidence is missing.

### WARNING

A PR is docs-only, test-only, or refactor-only and does not alter product behavior, but the reviewer should still verify that no hidden behavior change exists.

## Definition of Done

A Tradebot PR is not done until:

- intended behavior is documented
- edge purpose is clear
- tests prove the behavior
- negative tests prove fail-closed behavior
- broker/network/order paths remain impossible in tests
- focused test command passes
- relevant regression command passes
- QA Gate passes

## Non-Negotiable Rules

- No fix without regression proof.
- No feature without behavior proof.
- No trading module change without edge proof.
- No safety-sensitive change without fail-closed proof.
- No dashboard change without read-model truth proof.
- No execution change without broker/order impossibility proof.

## Docs-Only Exception

Docs-only PRs may skip code tests only when:

- no production code changes exist
- no runtime scripts change
- no test fixtures change
- no CI workflow changes that affect test execution exist

Docs-only PRs must still explain why code tests are not required.
