# Vulcan Production Hardening Maturity Model

## Purpose

This model prevents vague claims like hardened, safe, or production-ready.

A change is only more mature when behavior, safety, tests, and evidence improve together.

## Maturity Levels

### Level 0 — Basic

- behavior exists but contract is unclear
- tests check mostly shape or happy path
- invalid input may pass silently
- evidence is missing or vague

Allowed claim: basic implementation.

### Level 1 — Fragile

- intended behavior exists
- edge cases are weak
- negative tests are missing
- failures may be hidden by fallback or permissive defaults

Allowed claim: partial behavior exists but hardening is required.

### Level 2 — Contracted

- explicit behavior contract exists
- known invalid states are rejected
- tests prove main behavior
- evidence explains decisions

Allowed claim: contracted and test-backed.

### Level 3 — Hardened

- behavior is deterministic
- unsafe states fail closed
- negative tests cover known failure modes
- structured reasons are emitted
- evidence is rich enough for review

Allowed claim: hardened for scoped behavior.

### Level 4 — Production Grade

- all Level 3 criteria pass
- boundary risks are tested
- rollback path is clear
- CI gates protect regression
- operational evidence is stable and reviewable

Allowed claim: production-grade for the scoped contract.

## Required Upgrade Evidence

To move from Basic or Fragile to Contracted:

- explicit contract
- focused behavior test
- failure reason for invalid input

To move from Contracted to Hardened:

- negative tests
- fail-closed behavior
- structured rejection reasons
- evidence assertions when output changes

To move from Hardened to Production Grade:

- regression coverage for exact issue
- CI gate proof
- safety review when actionability is involved
- rollback plan

## Downgrade Triggers

A change must be considered downgraded if it:

- weakens a test
- removes a rejection reason
- makes fallback more permissive
- hides broken input behind default success
- changes output shape without evidence contract proof
- touches restricted behavior outside scope

## TradeBot-Specific Production Bar

For TradeBot, production-grade does not mean profitable.

It means the scoped behavior is safe, deterministic, reviewable, and protected from regression.
