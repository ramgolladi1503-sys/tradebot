# Hermes Stage 1 — Issue 7 T-1 Assembler Mutation Attacks

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Prove T-1 assembly rejects wrong-date, future, and incomplete prerequisite evidence
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Scope

Add an offline mutation harness for existing Issue 7 assembler guards. The harness must mutate temporary copies only and invoke existing behavior tests. No production source, data, or runtime artifact may be modified.

## Invariants under attack

1. Source ancestor trading date must match the resolved prior eligible session.
2. Source and derived prerequisite availability must not exceed the decision epoch.
3. Every required `(strategy_id, field)` prerequisite must be present exactly once.

The existing tests are authoritative for these failure contracts:

- `test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence[wrong_source_session-SOURCE_ANCESTOR_IDENTITY_MISMATCH]`
- `test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence[future_evidence-T1_EVIDENCE_NOT_AVAILABLE_AT_DECISION]`
- `test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence[missing-MISSING_T1_PREREQUISITE_FIELD]`

## Safety and limits

- Mutations occur in a temporary directory and never alter the checkout source.
- Do not generate T-1 values or alter the runtime loader, calendar, strategy logic, risk/feed gates, token universe, or order/broker authority.
- A killed mutation proves only that its targeted test detects that specific guard removal. It does not prove external data authority, holiday-calendar completeness, source authenticity, or successful live prerequisite staging.
- Issue 7 source and manifest authority remain `UNKNOWN`.

## Acceptance

The unmodified target tests pass first. Each of the three isolated guard-removal mutants must make its matching test fail for the expected contract, and the harness must reject a surviving mutant or collection/setup failure. Temporary files are removed automatically. `git diff --check` passes.

**Hermes verdict:** narrow offline test-harness work approved; no runtime or prerequisite behavior is authorized to change.
