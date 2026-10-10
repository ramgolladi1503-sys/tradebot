# TradeBot Work Item Template

Use this template for every Epic, Feature, Story, Bug, or Task.

## Identity

- Work Item ID:
- Type: EPIC / FEATURE / STORY / BUG / TASK
- Parent Epic:
- Parent Feature:
- Title:
- Current State:
- Priority:

## Business Goal

Why does this work matter to the TradeBot product?

## Current Behavior

What happens now?

## Expected Behavior

What must happen after completion?

## In Scope

-

## Out of Scope

-

## Dependencies

-

## Requirement Traceability

| Requirement ID | Requirement | Source | Acceptance criterion |
|---|---|---|---|
| | | | |

## Safety / Risk Constraints

- Broker/order impact:
- LIVE/PAPER/SIM impact:
- Risk-gate impact:
- Feed-freshness impact:
- Data/evidence impact:
- Required human approval:

## Architecture Impact

- Components touched:
- Interfaces/contracts affected:
- Existing infrastructure reused:
- New infrastructure required and why:
- High-risk paths touched:

## Acceptance Criteria

- [ ]
- [ ]

## Development Plan

- Allowed paths:
- Forbidden paths:
- Expected implementation:
- Required developer tests:

## QA Attack Plan

- happy path
- negative path
- boundary conditions
- stale/missing/corrupt data
- state-transition failures
- concurrency/order failures where applicable
- regression targets

## UAT Criteria

-

## Release Gates

- [ ] Requirements traceable
- [ ] Architecture approved
- [ ] DEV_VERIFIED
- [ ] QA_PASSED
- [ ] SENIOR_QA passed
- [ ] UAT passed
- [ ] PRODUCT_ACCEPTED
- [ ] CI_GREEN
- [ ] rollback/limitations documented

## Rollback Plan

-

## Evidence

- Tests:
- Logs/reports:
- Agent review evidence:
- PR:

## Claim-level Evidence Standard

For material work, add the `extensions.evidence_standard` object from
[`governance/evidence/templates/evidence_record.json`](../../governance/evidence/templates/evidence_record.json)
to the canonical work-item JSON. Register each claim and source in
`governance/evidence/CLAIM_REGISTRY.json` and
`governance/evidence/SOURCE_REGISTRY.json`. Use `UNVERIFIED` until G1 source,
G2 correctness, G3 adversarial, and G4 independent evidence are linked to the
existing hash-sealed delivery evidence records.

For a justified non-applicable work item, set `applicability` to
`NOT_APPLICABLE`, provide `applicability_reason`, and leave claims empty. This
status is not equivalent to a verified result.
