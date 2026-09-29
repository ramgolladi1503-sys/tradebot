# Next Read-Only Live Verification Runbook

Status: `LIVE_VERIFICATION_PENDING`. This document is an operator-controlled future procedure; it was not executed in this task.

## Preconditions

- Obtain separate, explicit operator authorization for the observation window and named evidence root. This runbook itself grants no runtime or broker authority.
- Inventory processes, working directories, and recurring OS/app launch schedules immediately before the observation. If any process may write the selected run root, do not inspect its files. If a recurring trigger can relaunch into the selected root, defer until the operator has resolved that schedule. Do not stop, signal, restart, relaunch, or modify the trigger from this procedure; defer to the operator's normal session procedure.
- Confirm repository SHA with `git rev-parse HEAD`, branch with `git branch --show-current`, and working-tree status with `git status --short --branch`. Record all three in the run record. The deployed/observed producer SHA must match the approved SHA or the run is `BLOCKED_RUNTIME_SHA_MISMATCH`.
- Confirm the observer's safety contract before allowing observation: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`, `allowed_for_live_execution=false`. Any missing, true, or contradictory field blocks the observation.
- Do not retrieve or display credentials, read token values, invoke broker endpoints, perform broker login/profile calls, or access order APIs. The procedure consumes only local observer output from an already operator-authorized read-only session.
- Select one approved evidence root. Record session ID/date, venue, calendar ID/version, instrument and contract identity, producer SHA, schemas, root device, and expected manifest names. Reject arbitrary-root discovery, symlinks as authority, unknown schema versions, and files whose source hashes do not close.
- Require the run identity and shutdown artifact to agree that the runtime completed. A missing PID, `STOP_REQUESTED` marker, or process identity marked `RUNNING` is insufficient. Require `final_seal=COMPLETE`, `phase=CLOSED`, all drain-complete flags true, queue/pending/in-flight counts zero, workers terminated, and final flush complete. If any differ, label `RUNTIME_SHUTDOWN_FAILED` and do not consume dependent runtime artifacts. For files written by the observation, wait until the owning runtime has naturally completed and released them. Confirm no writer process and no open file handle before hashing or reading. Capture file size, inode, modification time, and SHA-256 before and after inspection; any difference makes that artifact `UNSTABLE_SOURCE` and blocks its dependents. Never copy changing bytes and call the copy sealed.
- Resolve exact CAS selection semantics and capture a durable source tick/event ID plus canonical payload hash before attempting CAS qualification. Compare source event time and precision, selected event time, and local receive time separately. If source-to-price identity is absent, record `BLOCKED_SOURCE_BINDING`; do not apply a lateness tolerance not in the frozen contract.
- Resolve the previous eligible session through an authoritative venue/instrument calendar artifact and verify its hash/version. Require the exact Opening Drive T-1 15:29 regular-session NIFTY futures bar and strict contract-key equality. Require the complete frozen NIFTY50 daily series and independent SMA200 recomputation for S1/S4. Missing, stale, mixed-contract, or unsealed input remains field-specific `BLOCKED_SOURCE_EVIDENCE`.

## Measurements

For each instrument/token and every checkpoint, record intended subscription, callback count, valid source-event ID/hash count, first/last source-event time, first/last receive time, max observed source-event interarrival, selected/freshness time, transformation, coverage interval, explicit process downtime, rejection reason, and downstream effect. Reconcile counts from source events through tick store, pulse, evidence, strategy observation, candidate, decision, and trade-truth using shared IDs/hashes only. Publish unmatched counts and rates at every edge; never infer an identity from token/time proximity.

Only classify an interval as a missed-feed gap when a versioned, frozen per-token cadence/coverage contract supplies the expected interval and tolerance. Otherwise report the measured interval and `UNKNOWN_EXPECTED_CADENCE_NOT_PROVIDED`; do not turn it into a strategy blocker or a readiness pass by assumption. Subscription-count equality is not coverage proof.

For every run and session manifest, independently verify canonical artifact hash, node hashes, parent hashes, schema version, session/instrument/contract identity, calendar predecessor, dependency closure, availability at decision epoch, and index entry. Record verifier command/version, full output, exit code, and manifest SHA. A verifier error, missing node, conflict, future ancestor, unstable artifact, or unsupported schema blocks affected dependents; structural closure failure blocks the manifest.

## Acceptance

- Same-day restart references only verified same-session immutable ancestors; prior-day CAS never becomes today's CAS baseline.
- Previous-session prerequisites refer to actual eligible-session ancestors and exact hashes; no date subtraction or contract stitching.
- Readiness is per strategy and field, as-of constrained, and separate from entry eligibility. Expired windows produce no backdated candidates.
- Independently reopen each graph manifest and verify all hashes, dependency closure, schema, session/instrument identity and temporal constraints.
- Require observed producer SHA to equal the approved integration SHA and no recurring writer trigger to target the same root during verification. Require exact end-to-end source-event joins for every claimed feed-to-decision path; state `UNKNOWN` for missing IDs or unobservable consumers. Report expected and observed row counts per edge, plus explicit unmatched reasons.
- Keep the session status `PARTIAL` if any artifact is unstable, any cadence contract is missing, any downstream join is unknown, or any strategy-specific input is blocked. Do not convert a synthetic fixture result into runtime evidence.
- Preserve zero candidates and blocked states when gates fail. Do not access order APIs, create/modify/cancel orders, or promote paper/live authority.

Archive operator-approved read-only evidence and verifier output outside protected raw run folders. Do not edit source artifacts in place.

## Required run record

Store the following append-only summary beside (not inside) the raw run directory:

```text
run_id, trading_session_id, venue/calendar/version, instrument/contract identity
approved producer SHA, observed producer SHA, start/end time with clock domain
evidence root and source artifact paths/sizes/hashes/stability result
safety-contract fields and result
per-token intended/observed/event-valid counts and measured time ranges
per-edge lineage expected/observed/unmatched counts and reasons
graph verifier version, command, exit code, manifest/index hashes
per-strategy/per-field readiness and first blocking ancestor
V01–V22 result updates, source authority, and unresolved UNKNOWN/BLOCKED reasons
read_only=true, is_order_action=false, broker_api_called=false
broker_write_authority=false, order_authority=false, paper_authorized=false
live_authorized=false, allowed_for_live_execution=false
```

The final operator summary must distinguish `REPOSITORY_VERIFIED`, `DATA_VERIFIED`, `INDEPENDENTLY_DERIVED`, `LIVE_VERIFICATION_PENDING`, `UNKNOWN`, and `BLOCKED`. This procedure does not itself authorize entering paper/live modes or any execution behavior.
