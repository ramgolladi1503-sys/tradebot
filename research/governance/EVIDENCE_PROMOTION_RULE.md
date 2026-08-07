# Evidence Promotion Rule

Research authority advances only through registered evidence.

## Canonical Ladder

`Speculation -> Hypothesis -> Supported Hypothesis -> Certified Claim -> Operational Knowledge`

Skipping levels is prohibited.

## Promotion Requirements

A promotion decision must reference:

- the Claim ID and current version;
- the exact source and destination lifecycle states;
- new Evidence IDs introduced since the prior state;
- the Experiment IDs and Dataset IDs that produced that evidence;
- applicable calibration artifacts;
- attack results and unresolved destroyers;
- the authority grade before and after the decision;
- the Decision ID authorizing the transition.

## Evidence Quality Rules

Evidence used for promotion must be reproducible, provenance-complete, scoped to the claim, and generated under a procedure compatible with the stated inference.

Correlated artifacts from the same experiment do not automatically count as independent evidence. Repeated parameterizations of one dataset do not automatically count as replication.

## Contradictory Evidence

Contradictory evidence must be registered and adjudicated before promotion. It may reduce confidence, narrow scope, block promotion, trigger invalidation, or require a new claim version.

## No Evidence Recycling

The same evidence cannot be represented as “new” merely by reformatting, rerunning identical analysis without a scientific reason, or changing report language.

## Decision Outcome

Every attempted promotion ends with one of: `PROMOTE`, `HOLD`, `DEMOTE`, `REJECT`, `INVALIDATE`, or `SUPERSEDE`, with reasons recorded.
