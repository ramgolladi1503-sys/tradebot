# Hermes Contract — Issue 8 Malformed Source Event ID

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**scope:** fail-closed validation of untrusted `source_event_id` values in the offline CAS primitive producer and verifier
**requested_paths:** `core/cas_primitive_producer.py`, `tests/test_cas_primitive_producer.py`, this contract, and Issue 7–11 evidence artifacts
**forbidden_paths:** broker/order/risk/feed runtime, credentials, strategy logic, live/paper authority, captured historical artifacts
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`

## Evidence and defect

Independent adversarial review reproduced that `_valid_tick` calls `.endswith` on `source_event_id` without first requiring a string. A malformed value can raise `AttributeError` instead of returning a fail-closed rejection. `verify_primitive` has the same unguarded assumption. This is a repository-verified offline input-validation defect; it does not explain or repair the historical missing CAS heritage.

## Contract

At both ingestion and persisted-row verification boundaries, a source event ID must be a non-empty string before suffix binding is attempted. Missing, empty, or non-string values must be rejected without throwing. The producer must persist only its existing terminal blocked result for invalid input; the verifier must return a negative validation result. Valid IDs keep the existing token/hash suffix contract unchanged.

No changes to CAS source authority, timestamp selection, persistence identity, or recovery eligibility are authorized.

## Acceptance proof

1. Exercise missing, empty, integer, boolean, and arbitrary-object IDs through `_valid_tick`/capture and `verify_primitive`.
2. Prove each malformed input returns blocked/invalid without leaking an exception or writing a captured primitive.
3. Preserve a valid source-event-bound positive case and all existing CAS tests.
4. Keep Issue 8 historical authority `UNKNOWN`; synthetic validation is not captured runtime proof.
