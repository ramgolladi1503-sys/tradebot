# Next Read-Only Live Verification Runbook

Status: `LIVE_VERIFICATION_PENDING`. This document is an operator-controlled future procedure; it was not executed in this task.

## Preconditions

- Obtain explicit operator authorization for a read-only observation session. Do not infer authority from this runbook.
- Do not restart, stop, signal, or relaunch an existing runtime. If an authorized fresh session cannot be obtained without affecting a running process, defer.
- Confirm the selected code SHA and the read-only runtime safety contract. Required output invariants: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `broker_write_authority=false`, `order_authority=false`, `allowed_for_live_execution=false`.
- Select only an approved evidence root; verify its session identity, venue calendar version, instrument/contract identity, schema, and immutable source hashes before reading.
- Resolve exact CAS selection semantics and capture a durable source tick/event ID plus payload hash before attempting CAS qualification. If source-to-price identity is absent, record `BLOCKED_SOURCE_BINDING`.
- Resolve prior eligible session through an authoritative venue calendar. Require the exact Opening Drive T-1 15:29 regular-session NIFTY futures bar and strict contract-key equality. Require the full frozen NIFTY50 daily series and independently recomputed SMA200 for S1/S4. Any missing input remains field-specific `BLOCKED_SOURCE_EVIDENCE`.

## Measurements

For each instrument/token and every checkpoint, record intended subscription, actual observed tick identity, source/event epoch and precision, local receive epoch, selected/freshness epoch, transformation, source hash, coverage interval, explicit gaps, rejection reason and downstream effect. Reconcile pulse cadence to first/last event times and per-token intervals; subscription counts alone do not establish coverage.

## Acceptance

- Same-day restart references only verified same-session immutable ancestors; prior-day CAS never becomes today's CAS baseline.
- Previous-session prerequisites refer to actual eligible-session ancestors and exact hashes; no date subtraction or contract stitching.
- Readiness is per strategy and field, as-of constrained, and separate from entry eligibility. Expired windows produce no backdated candidates.
- Independently reopen each graph manifest and verify all hashes, dependency closure, schema, session/instrument identity and temporal constraints.
- Preserve zero candidates and blocked states when gates fail. Do not access order APIs, create/modify/cancel orders, or promote paper/live authority.

Archive operator-approved read-only evidence and verifier output outside protected raw run folders. Do not edit source artifacts in place.
