# PR858 to PR815 Current-Main Prospective Evidence Reconstruction

mode: OFFLINE_IMPLEMENTATION_REVIEW
candidate_id: PR858_PR815_CURRENT_MAIN_SUCCESSOR
decision: RECONSTRUCT_AND_VALIDATE
reason: Combine the independent attestation producer and prospective evidence finalizer on the exact current main base.
timestamp: 2026-08-31T23:30:00+0530
is_order_action: false
broker_api_called: false
source: exact current main SHA fc5ca9288aaf19697cb089d235f8214cc178dc75 plus offline focused tests

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Current-main prospective evidence reconstruction
- scope: Read-only evidence producer and immutable completed-session finalizer only.
- requested_paths: producer, finalizer, focused tests, focused workflow, research documentation, and this review record.
- allowed_paths: The listed paths only.
- forbidden_paths: Broker/order execution, strategy/ranking/risk, credentials, launchers, live authorization, and evidence artifacts outside the explicit output root.
- broker_connectivity_authorized: false
- broker_write_authority: false
- order_authority: false
- paper_authorized: false
- live_execution_authorized: false
- expected_broker_methods: none
- forbidden_broker_methods: all order, position, holdings, funds, and broker-write methods
- credential_boundary: no credentials or token contents are read, logged, copied, or persisted

## Design and Scope

The producer trusts only the existing read-only WebSocket subscription lifecycle seam for the three repository-pinned index identities. The finalizer independently verifies the signed attestation, exact code SHA, session chronology, canonical identities, complete live-websocket provenance, 375-minute continuity, OHLC validity, immutable semantic hashing, and idempotent writes.

The implementation is dormant until a separately authorized read-only observation wires the producer and supplies its output. It does not place orders, change trading decisions, or authorize paper/live execution.

## Scope Guard

No runtime execution path, broker adapter, strategy, ranking, risk, credential, or launcher file is changed. The workflow performs only exact-checkout compilation and focused offline tests.

## Grill Me Review

Unit tests, replay fixtures, and caller-declared bar provenance cannot establish fresh live proof. Missing attestation, invalid signatures, wrong tokens, stale/future chronology, incomplete bars, synthetic provenance, and immutable conflicts fail closed.

## Hermes Review

The producer and finalizer have separate trust responsibilities: subscription lifecycle evidence is independently signed, while bar evidence is accepted only when it matches that attestation. The verification key is read from trusted runtime configuration and cannot be selected by the attestation caller.

## GSD Review

This successor is reconstructed from exact current main `fc5ca9288aaf19697cb089d235f8214cc178dc75`. Stale PR base references and contradictory historical review claims are excluded. No silent fallback or synthetic live evidence is introduced.

## QA / Safety Review

Focused tests cover identity, lifecycle, signing, timestamps, SHA validation, tamper/conflict/idempotency behavior, session completeness, provenance, chronology, and safe-finalizer failure containment. All tests are offline and make no broker calls.

## Safety Contract

broker_write_authority=false; order_authority=false; paper_authorized=false; live_execution_authorized=false; orders_placed=0; orders_modified=0; orders_cancelled=0; LIVE_PROOF=NOT_PROVIDED; SHADOW_LIVE_VALID=false; STRUCTURAL_EDGE_CERTIFIED=false.

## Acceptance Proof

- Exact current-main base: `fc5ca9288aaf19697cb089d235f8214cc178dc75`.
- Focused producer/finalizer tests: required and offline.
- Exact SHA, source identity, immutable, and idempotency checks: required.
- Repository protected checks: required.
- Broker API calls: 0; order actions: 0.

## What This PR Does Not Prove

This implementation does not prove that a live market session occurred, does not establish prospective support, does not certify an edge or profitability, and does not grant paper/live execution authority. Historical, replay, synthetic, or unit-test evidence cannot promote those claims.

## Runtime Proof Required After Merge

A separately authorized exact-SHA read-only market session must wire the producer, capture fresh subscription lifecycle evidence for all three canonical indices, complete the session, and independently verify the finalizer artifact. Until then, live certification remains blocked.

## Human Approval

Merge remains subject to normal protected branch checks and human-controlled authorization. No force, admin, or gate-bypass merge is authorized.
