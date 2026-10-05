---
name: Feature request
about: Propose a Tradebot improvement
labels: enhancement
---

## Work hierarchy

- Type: FEATURE / STORY / TASK
- Parent Epic:
- Parent Feature:
- Proposed Work Item ID:
- Priority:

## Business goal

Why does this matter to the TradeBot product?

## Current behavior

What exact pain point or limitation exists now?

## Expected behavior

Describe how the system should behave after this feature exists.

## In scope

-

## Out of scope

-

## Dependencies

-

## Area affected

- [ ] Market feed reliability
- [ ] Contract resolution
- [ ] Signal generation
- [ ] Ranking / opportunity quality
- [ ] Execution gate
- [ ] Risk controls
- [ ] Dashboard / UI
- [ ] Reports / reconciliation
- [ ] ML/RL/data workflow
- [ ] CI / release process
- [ ] Documentation

## Acceptance criteria

- [ ] Behavior is testable offline or in paper mode where applicable
- [ ] Failure state is visible to the operator
- [ ] Does not weaken risk controls
- [ ] Does not hide stale feed, stale LTP, or contract-resolution failures
- [ ] Acceptance criteria are measurable and traceable

Additional criteria:

- [ ]

## Architecture / safety impact

- Existing infrastructure to reuse:
- High-risk paths potentially affected:
- Broker/order impact:
- LIVE/PAPER/SIM impact:
- Data/evidence impact:

## QA attack plan

List how QA should try to break this feature, not merely confirm the happy path.

-

## UAT expectation

What business behavior proves the feature is acceptable?

## Validation plan

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

Add targeted tests/scripts as required.

## Tradeoff / risk

What can go wrong if this feature is built poorly?

## Notes

Add references, screenshots, examples, or related issues.
