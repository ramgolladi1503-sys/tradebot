# Autonomous loop build eligibility contract V1

## Scope

This change separates implementation scheduling from checkpoint certification.
An upstream task at `IMPLEMENTATION_VALID`, `ADVERSARIAL_VALID`,
`INTEGRATION_VALID`, `REGRESSION_VALID`, `INDEPENDENTLY_VERIFIED`, or `CI_GREEN`
may release a dependent task for implementation. `SEALED` remains a valid
provisional predecessor as well.

The existing `eligible_task_ids` path remains certification-oriented: only a
strict terminal outcome (`SEALED`, or an explicitly declared honest terminal
outcome) releases certification dependencies. No provisional state can release
sealing or make CI evidence appear complete.

## Safety and non-scope

The supervisor remains a pure in-memory governance component. It has no shell,
network, credential, broker, order, paper, or live authority. Feed and WS
behavior are untouched.

## Validation

Focused tests cover integration-valid release, provisional-state separation,
and fail-closed blocked/generic-invalidated behavior. The evidence is bound to
the candidate commit that contains this document and the corresponding code
and tests.
