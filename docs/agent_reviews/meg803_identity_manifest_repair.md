# MEG #803 Surgical Identity and Canonical Manifest Repair

source: docs/agent_reviews/meg803_identity_manifest_repair.md
title: MEG #803 producer identity propagation and canonical sealed-root verification
scope: parent commit-SHA propagation, fail-closed producer identity, and #803 consumption of the canonical PR #782 sealed-root contract
requested_paths:
  - scripts/run_market_event_graph_live_session_v1.py
  - core/kite_read_only_observation_runtime.py
  - core/meg_request_scoped_causality.py
  - tests/test_meg_request_scoped_causality.py
  - tests/test_verify_meg_request_scoped_causality_cli.py
allowed_paths:
  - scripts/run_market_event_graph_live_session_v1.py
  - core/kite_read_only_observation_runtime.py
  - core/meg_request_scoped_causality.py
  - tests/test_meg_request_scoped_causality.py
  - tests/test_verify_meg_request_scoped_causality_cli.py
  - docs/agent_reviews/meg803_identity_manifest_repair.md
forbidden_paths:
  - core/market_event_graph*
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/**
  - config/**
  - credentials.py
  - .env

## High-Risk Path Review

The runtime changes are limited to provenance and evidence validation. The
producer SHA is computed once by the parent from the repository HEAD and is
passed to the child through `TRADEBOT_COMMIT_SHA`; operator-provided values do
not override it. Blank producer identity fails before lifecycle evidence is
written. The verifier delegates sealed-root integrity to the existing
canonical PR #782 verifier and then performs the existing #803 causal checks.

No broker, order, risk, feed, strategy, subscription, OHLC, or execution
behavior is changed. All new/retained evidence remains read-only and carries
`broker_write_authority=false` and `order_authority=false`.

## Acceptance Evidence

- Focused MEG lifecycle, operator, bridge, primitive, verifier, and canonical
  seal integration tests pass.
- Blank producer SHA is rejected before primitive persistence.
- Canonical `artifact_manifest.json` + `SHA256SUMS` + `SEALED` is required;
  legacy `manifest.json` does not satisfy the verifier.
- `git diff --check` and Python compilation pass.

## Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: MEG #803 identity and canonical manifest repair

## Scope Guard

Only the requested two contracts and their focused tests are in scope.

## Grill Me Review

The repair must not claim a fresh live certification until a new session
persists the exact final SHA and passes #803, #782, and any permitted #783 gate.

## Hermes Review

The parent is the sole producer-identity authority. Canonical PR #782 sealed
root verification is the sole seal authority.

## GSD Review

Implementation is limited to the listed paths and is test-gated before freeze.

## QA / Safety Review

Blank identity fails closed; canonical seal tampering, missing markers, and
undeclared artifacts remain failures. No order or broker-write authority is
introduced.

## Acceptance Proof

The focused suite and canonical seal integration test are required to pass on
the final commit.

## Runtime Proof Required After Merge

A fresh bounded live recertification must prove the final SHA in the
presession manifest, process identity, and every #803 primitive before seal.

## What This PR Does Not Prove

It does not prove profitability, structural edge, options edge, execution
viability, or successful broker execution.

## Human Approval

Fresh live recertification remains a separate operator-approved action after
the repaired SHA is pushed and remotely verified.

## Not Touched

The historical 2026-08-10 sealed evidence root is unchanged. No live session,
broker call, order action, or live-authority configuration was performed by
this repair.
