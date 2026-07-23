# Option E2E Authority Oracle v4.1

## Scope

Subagent I1 implemented an independent, research-only authority oracle under `research/option_e2e_recertification_v4/authority_oracle_v4_1/`.

Owned paths:

- `research/option_e2e_recertification_v4/authority_oracle_v4_1/**`
- `tests/research/option_e2e/test_authority_oracle_v4_1.py`
- `docs/agent_reviews/option_e2e_authority_oracle_v4_1.md`

No shared resolver, broker, runtime, strategy, credential, or audited evidence artifact was edited.

## Design

The oracle verifies composite option-contract authority from independent evidence records:

- target contract identity
- point-in-time master evidence
- quote filename evidence
- quote row evidence
- source manifest evidence
- observed universe evidence
- independent lot-size evidence

It fails closed with explicit reason codes. Full quote identity can prove observed contract existence, but universe completeness is a separate gate and remains false when expected identities are missing.

## Safety Invariants

- `allowed_for_live_execution=false`
- `broker_api_called=false`
- `is_order_action=false`
- no broker imports
- no order actions
- no runtime wiring
- no strategy threshold changes
- no current-master-only certification

## Test Coverage

Tests cover:

- current master alone fails
- quote filename alone fails
- quote row without expiry fails
- full quote identity proves observed existence but not universe completeness
- mismatched token/symbol fails
- mismatched filename/row metadata fails
- post-expiry quote fails
- future-created manifest fails
- duplicate conflicting identities fail
- incomplete observed universe is surfaced
- lot size is independently gated
- complete independent authority passes with fail-closed flags

## Rollout Notes

This is an offline research verifier only. To use it in a later PR, consume the typed oracle result as an evidence gate and require human review before any runtime integration.
