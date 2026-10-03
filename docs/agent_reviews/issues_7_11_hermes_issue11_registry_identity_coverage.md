# Hermes Contract — Issue 11 registry domain-to-identity coverage

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Reject candidate feed declarations without identities for every required domain
**scope:** `core/candidate_feed_dependencies.py` registry validation and eligibility only
**requested_paths:** `core/candidate_feed_dependencies.py`, `tests/test_candidate_feed_dependencies.py`, `scripts/verify_issues_7_11_issue11_registry_identity_mutation.py`
**allowed_paths:** The requested paths and the corresponding Issues 7–11 evidence artifacts listed in the GSD plan.
**forbidden_paths:** Broker/order/risk code, strategy logic, runtime feed producers, token-universe configuration, credentials, live runtime files, and any modification that makes partial declarations execution eligible.
**expected_tests:** Candidate dependency registry tests; symbol execution safety tests; focused Issue 11 isolation tests; isolated validator mutation.
**acceptance_proof:** A verified declaration with a nonempty required domain and no matching identity is rejected by validation and returns non-executable blocked resolution. Removing the coverage invariant in an isolated temporary source copy makes the regression fail. Existing registry declarations remain valid and their eligibility is unchanged.

## Finding

`validate_registry_entries` validates `required_domains` and `required_identities` independently. A verified entry with `required_domains=("INDEX_OPTIONS",)` and `required_identities=()` therefore passes validation. `resolve_candidate_dependencies` then iterates over zero identities and can return `execution_eligible=True` from an empty identity-health mapping. This is a concrete fail-open at the candidate dependency contract boundary.

## Contract

1. The set of domains in `required_identities` must exactly cover `required_domains`; missing or extra identity domains make the registry invalid.
2. Eligibility itself must require complete domain-to-identity coverage as defense in depth; malformed entries must not depend on a caller remembering to run validation first.
3. A declared `(domain, None)` is a known unresolved dynamic identity. It counts for schema coverage but remains ineligible.
4. String identities must be nonempty, non-whitespace, and already trimmed. A health-map entry under an empty or padded key is not canonical identity evidence.
5. The resolver returns `UNKNOWN_BLOCKED` for an invalid registry and never treats an empty mapping as evidence that a required domain is healthy.
6. Current candidate declarations, authority statuses, freshness limits, and execution scopes are not broadened or rewritten.

## Safety and blast radius

The change closes malformed registry metadata at a pure validation boundary. Valid existing registry entries retain their current status. No market data is reinterpreted, no strategy evaluation is altered, and no execution authority is granted. Read-only verification only; no broker or order action.

## Rollback and configuration

Rollback is limited to reverting the domain-coverage invariant and its tests. No configuration keys or migrations are introduced. Because this is a fail-closed tightening, a malformed declaration becomes blocked instead of eligible.

## Human approval boundary

This contract does not authorize runtime wiring, candidate promotion, broker integration, changes to strategy dependencies, or any live/paper authority. Any such follow-up requires a separate Hermes contract and explicit scope.
