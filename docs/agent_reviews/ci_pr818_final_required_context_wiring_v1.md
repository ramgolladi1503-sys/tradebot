# Agent Review: PR818 Final Required-Context Wiring

mode: CI_GOVERNANCE_ONLY
candidate_id: ci/pr818-final-required-context-wiring-v1
decision: GOVERNANCE_REVIEW_REQUIRED
reason: Route required PR contexts through current-base exact-SHA governance without changing PR818.
timestamp: 2026-08-14T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: independent_ci_governance_review

## Agent Work Contract

Only workflows, CI validators, and focused CI tests are in scope.

## Scope Guard

No core runtime, strategy, broker, order, risk, feed implementation, credential, or PR818 file is changed.

## Grill Me Review

The required contexts must remain fail-closed and must reject wrong SHA, missing evidence, unauthorized high-risk changes, and source whitespace defects.

## Hermes Review

Current main and the exact candidate head are fetched independently; synthetic merge refs are not authority.

## GSD Review

This is a separate governance branch and does not update, rebase, or commit to PR818.

## QA / Safety Review

No secrets or write permissions are used by governance jobs. Candidate execution remains in an unprivileged read-only workflow.

## High-Risk Path Review

The scope validator distinguishes unauthorized high-risk changes from governed changes with focused tests.

## Acceptance Proof

Local validation passes exact SHA binding, base-authoritative review, runtime scope, diff classification, and negative controls.

## Runtime Proof Required After Merge

This PR does not certify live behavior, profitability, broker readiness, or reconnect coverage.

## What This PR Does Not Prove

It does not alter or re-certify the frozen PR818 implementation.

## Human Approval

Required before merging this governance PR and before merging PR818.
