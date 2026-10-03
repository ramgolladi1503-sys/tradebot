# Hermes Contract — Issue 8 Persisted CAS Instrument Identity

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**scope:** enforce the CAS primitive's fixed NIFTY underlying identity when verifying persisted rows
**requested_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, this contract, and Issue 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategy logic, token-universe policy, live/paper authority
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Reproduction

An offline adversarial row was modified from `NIFTY` to `BANKNIFTY`; its event payload hash, source-event ID suffix, and outer record hash were recomputed consistently. `verify_primitive(..., underlying_token=1)` returned `(True, "ok")`. The capture path already requires `underlying_symbol == "NIFTY"`, so persisted verification was weaker than capture.

## Contract

Every verified persisted CAS primitive must have `underlying_symbol == "NIFTY"`, and its event payload must continue to bind that exact symbol, the configured underlying token, price, and source timestamp. An internally self-consistent hash chain does not authorize another instrument identity. Reject with a stable identity failure before admission.

This closes only a repository-level identity validation gap. It does not authenticate external feed provenance or establish historical CAS recovery authority.

## Acceptance proof

1. Reproduce the wrong-symbol row after recomputing all existing content hashes and event-ID suffixes.
2. Require verification to reject the row with an identity reason.
3. Preserve valid NIFTY capture/verification and token-binding rejection tests.
4. Run the focused CAS producer suite; retain Issue 8 historical source authority as `UNKNOWN`.
