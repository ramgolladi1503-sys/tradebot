---
name: Feature request
about: Propose a Tradebot improvement
labels: enhancement
---

## Feature summary

Describe the feature in one or two sentences.

## Problem it solves

What exact pain point does this remove?

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

## Proposed behavior

Describe how the system should behave after this feature exists.

## Acceptance criteria

- [ ] Behavior is testable offline or in paper mode
- [ ] Failure state is visible to the operator
- [ ] Logs/dashboard fields are clear
- [ ] Does not weaken risk controls
- [ ] Does not hide stale feed, stale LTP, or contract-resolution failures

## Validation plan

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

Add any targeted tests or scripts needed.

## Tradeoff / risk

What can go wrong if this feature is built poorly?

## Notes

Add references, screenshots, examples, or related issues.
