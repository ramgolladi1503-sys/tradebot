# PR #941 Read-Only API Telemetry Policy Review

## Agent Work Contract

- `source_agent`: Hermes architecture and contracts; GSD scoped execution and verification.
- `action`: `DEFINE_CONTRACT`, `GENERATE_TESTS`, `GENERATE_PATCH`, `UPDATE_DOCS`.
- `title`: Keep read-only broker-call telemetry accurate while preserving fail-closed execution authority.
- `scope`: Code Excellence configuration, its boolean matcher, regression tests, and this review record.
- `requested_paths`: `.gsd-forensics.yaml`, `tools/code_excellence/cerberus_gate.py`, the two Code Excellence test files, and this document.
- `allowed_paths`: those requested paths only.
- `forbidden_paths`: broker adapters, feed runtime, credentials, strategy thresholds, order logic, dashboards, and protected runtime freeze policy.
- `expected_tests`: focused Cerberus and evidence-gate tests; unified Code Excellence against PR #939's changed-path set.
- `acceptance_proof`: read-only calls may set `broker_api_called=true` while order/write/live authority fields remain false; structured evidence paths still fail closed.

## Scope Guard

This change updates static policy and tests only. It makes `broker_api_called` factual transport telemetry and does not grant broker, order, paper, live, or execution authority. General review documents are excluded from structured evidence parsing; the configured runtime and report evidence directories remain covered.

## Grill Me Review

- Main risk: conflating an API transport call with an executed order. The policy keeps dedicated order-action, write-authority, order-authority, paper/live authorization, and live-execution fields fail-closed.
- Main limitation: the static Cerberus gate validates assignments that are present; behavioral runtime tests remain responsible for validating complete ledger records.
- No order, broker, credential, or live path is exercised by these tests.

## Hermes Review

The contract separates transport observation from action authority. A read-only query can truthfully record an API call. The policy must not rewrite that observation as false, and must retain independent false-valued authority fields.

## GSD Review

The implementation narrows evidence scanning to governed evidence/report directories, adds `read_only=true` checking with Python `is True` support, and tests both accepted read-only telemetry and rejected unsafe/invalid values. It does not alter runtime behavior.

## QA / Safety Review

Focused tests: 25 passed. The local unified Code Excellence run against PR #939's current changed-path set reported zero blocks using this policy. Hosted checks for this PR remain authoritative.

## Acceptance Proof

- A read-only ledger fixture records `read_only=true`, `broker_api_called=true`, and `is_order_action=true` while all order/write/live authority fields are false; Cerberus passes.
- A fixture that sets a required `read_only` value false is blocked.
- Python `assert value is True` assertions satisfy a `read_only=true` requirement; false values do not.
- Generic review prose is excluded from evidence scanning, while incomplete governed analytics evidence is blocked.
- The unified Code Excellence run against PR #939's current 55-path main-relative scope returned `total_blocks=0` with this policy.

## Runtime Proof Required After Merge

No product runtime proof is required because the change modifies only policy configuration, gate parsing, tests, and review documentation. Hosted checks must pass on the exact PR head. PR #938/#939 freeze or external preview checks are outside this PR's acceptance.

## What This PR Does Not Prove

- It does not prove runtime or broker readiness, T-1 source admission, a market observation, live safety certification, or strategy performance.
- It does not authorize API calls or order actions.
- It does not update or bypass the PR818 protected runtime freeze gate.

## Human Approval

The user requested work until CI is green and explicitly requested merging PRs #938 and #939. This document does not assert that PR #941 itself has been approved for merge. Do not merge #941 until its hosted checks pass and the user authorizes this prerequisite policy PR.
