# TradeBot Delivery Orchestrator

Use this workflow for every new TradeBot engineering/research request.

## 1. Classify

Classify the request as:

`EPIC | FEATURE | STORY | BUG | TASK`

Identify the affected product area and parent work item when known.

## 2. Business Analyst pass

Produce:

- business goal
- current behavior
- expected behavior
- in/out scope
- dependencies
- unresolved requirement gaps
- draft acceptance criteria

If the requirement is unsafe or materially incomplete, stop at `BLOCKED_REQUIREMENT`.

## 3. Product Owner pass

Confirm:

- product value
- priority
- scope boundaries
- measurable acceptance criteria
- whether UI/runtime/research work is actually required

Do not permit architecture expansion without product need.

## 4. Architecture pass

Hermes-compatible architecture roles review:

- reuse of current infrastructure
- interfaces/contracts
- data/state ownership
- concurrency/runtime impact
- high-risk paths
- safety invariants
- test/acceptance proof

State becomes `DESIGN_READY` only when architecture and acceptance gates are explicit.

## 5. Development pass

GSD-compatible developer role:

- implements only approved scope;
- touches only allowed paths;
- writes/updates tests;
- records exact validation;
- does not self-approve QA.

State: `IN_DEVELOPMENT -> DEV_VERIFIED`.

## 6. QA pass

QA attacks the implementation using the work item's QA plan plus `docs/tradebot_delivery/QA_PLAYBOOK.md`.

Any defect causes:

`QA_FAILED -> Development fix -> DEV_VERIFIED -> QA_IN_PROGRESS`

After retest, QA performs a new adversarial pass.

## 7. Senior QA

Senior QA independently reviews:

- defect closure;
- regression coverage;
- unsafe fallbacks;
- test weakening;
- scope creep;
- evidence quality.

## 8. UAT

Validate business behavior and acceptance criteria.

Backend-only work may use contract/report-based UAT.

## 9. Product acceptance

Product Owner checks the delivered behavior against the original work item.

No new requirements may be silently inserted at this stage.

## 10. Release

Release Manager:

- ensures PR and agent-review evidence exist;
- confirms required tests/gates;
- records limitations/rollback;
- waits for CI;
- marks `MERGE_APPROVED` only when required gates are green.

## 11. Production verification

Production/SRE verifies applicable runtime health/smoke checks.

Only then mark `DONE`.

## Required response for every orchestrated task

Report:

1. work-item identity and state;
2. role currently acting;
3. evidence produced;
4. blockers/failures;
5. next allowed transition.

Never claim a gate passed without evidence.
