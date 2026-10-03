# Hermes Contract — Issue 8 Numeric Instrument Token Identity

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**scope:** strict positive-integer token validation in offline CAS primitive capture and persisted verification
**requested_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, `scripts/verify_issues_7_11_issue8_mutations.py`, this contract, and Issues 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategy logic, token-universe policy, live/paper enablement
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Reproduction

Independent verification changed a captured row and payload instrument token from integer `1` to boolean `true`, recomputed the event hash, a source-event ID suffix bound to `1`, and the record hash. Python equality treated `True == 1`; `verify_primitive(..., underlying_token=1)` returned `(True, "ok")`.

## Contract

Instrument tokens at capture, persisted row, and event-payload boundaries must be exact Python integers greater than zero; booleans, floats, numeric strings, zero, negatives, and a missing configured token are not valid identities. Each accepted token must exactly equal the configured expected underlying token. Invalid identities fail closed with no captured primitive or exception.

This is repository-level type/identity validation only. It does not authenticate external source data or establish historical CAS recovery authority.

## Acceptance proof

1. Reject boolean, float, string, zero, negative, and missing expected tokens through ingestion and persisted verification.
2. Preserve valid positive integer token capture/verification and mismatched-token rejection.
3. Run the full focused CAS producer suite and keep historical Issue 8 source authority `UNKNOWN`.
4. Run the isolated mutation verifier and require each deliberately removed identity/type guard to be killed by its targeted regression.
