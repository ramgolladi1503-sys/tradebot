# Hermes contract — Issue 7 explicit calendar edge tests

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Prove T-1 resolver skips weekends and exchange holidays from explicit authority
**scope:** Offline tests and a temporary-copy mutation for `resolve_previous_eligible_session`.
**requested_paths:** `tests/test_market_heritage_graph.py`
**allowed_paths:** the requested test, `scripts/verify_issues_7_11_issue7_mutations.py`, this contract, its GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** production source/runtime wiring, external data files, broker/order/risk/feed paths, credentials, strategy thresholds, token-universe configuration.
**expected_tests:** a Monday target resolves Friday from explicit eligible-session records; a Wednesday target after an explicitly ineligible exchange holiday resolves the preceding eligible Monday. A temporary naïve calendar-day subtraction mutant must fail.
**acceptance_proof:** both expected predecessor dates resolve exactly; test remains based on explicit calendar authority and never derives a source price or prerequisite value.

## Invariant

The resolver must select the latest strictly earlier record that is explicitly `eligible=true` and `verified=true`, matching the target calendar ID/version, venue, and instrument ID. It must not infer a trading session from weekday arithmetic. A false or absent calendar authority remains blocked.

## Limits

These cases prove resolver behavior for supplied records only. They do not certify that the external calendar source is complete/correct for every date, establish futures data authority, stage T-1 values, or prove live prerequisite readiness. No production behavior changes are authorized.
