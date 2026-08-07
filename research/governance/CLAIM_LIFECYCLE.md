# Claim Lifecycle

Every research claim must occupy exactly one lifecycle state.

## States

1. `SPECULATION` — an untested idea worth preserving.
2. `HYPOTHESIS` — a registered falsifiable statement with destroyers and a planned experiment.
3. `SUPPORTED_HYPOTHESIS` — reproducible registered evidence supports the hypothesis within stated scope.
4. `CERTIFIED_CLAIM` — calibrated certification and independent attack requirements have been satisfied and a certification decision is recorded.
5. `OPERATIONAL_KNOWLEDGE` — economic and implementation gates have also passed and bounded downstream use is approved.
6. `REJECTED` — evidence is sufficiently inconsistent with the claim or required burden of proof failed.
7. `INVALIDATED` — prior evidence or process was contaminated, non-reproducible, or otherwise scientifically inadmissible.
8. `SUPERSEDED` — a newer registered claim replaces this one while preserving history.

## Transition Rules

- Promotions require new Evidence IDs and a Decision ID.
- Promotions may advance only one level at a time.
- Demotion may occur whenever new evidence weakens authority.
- `INVALIDATED` evidence may remain historically visible but cannot support promotion.
- A rejected hypothesis may be reformulated only as a new version or new Claim ID with explicit lineage; it may not be silently edited into success.

## Required Claim Record

Each claim record must identify: Claim ID, version, title, exact statement, lifecycle state, scope, target, horizon, population, provenance, supporting Evidence IDs, contradicting Evidence IDs, Experiment IDs, Dataset IDs, known weaknesses, destroyers, current authority grade, decision history, supersession lineage, owner, created timestamp, and last-review timestamp.
