# Tradebot Intelligence Layer Safety Boundaries

## Non-Negotiable Constraints

The Tradebot Intelligence Layer is read-only. It must analyze evidence and produce intelligence artifacts only.

It must never be allowed to become an implicit trading system, broker client, runtime controller, or strategy tuner.

## Prohibited Actions

The Intelligence Layer must not:

- call broker APIs
- place orders
- modify runtime state
- restart feed
- modify lock files
- change strategy thresholds
- change risk limits
- change ranking thresholds
- call external trading APIs
- auto-create pull requests
- auto-merge pull requests
- auto-create commits
- mutate live session files except its own `.runtime/intelligence/` outputs
- make automatic trading decisions
- bypass manual approval
- infer safety from missing data

## Allowed Actions

The Intelligence Layer may:

- read runtime files
- read logs
- read evidence JSON
- read analytics artifacts
- read agent-review documents
- produce reports
- produce issue drafts
- produce recommendations
- produce cross-session memory
- classify insufficient evidence
- classify unknown safety state
- suggest tests for a future human-approved change

## LIVE Mode Policy

In LIVE mode, the Intelligence Layer remains read-only. LIVE mode increases the required safety strictness; it does not grant extra permissions.

If LIVE mode evidence is ambiguous, the system must report the safety state as unknown or unsafe to conclude.

Two examples:

1. If `LIVE_AUDIT_ONLY=1` is expected but missing from evidence, the Risk and Safety Boundary Agent must not assume audit-only safety.
2. If an order-path artifact appears during audit-only mode, the system must classify it as a critical safety violation until proven otherwise.

## Audit-Only Policy

Audit-only means the system may observe and report. It does not mean the system may place, modify, cancel, or simulate real broker orders through live APIs.

The Intelligence Layer must not use audit-only mode as a reason to touch order code paths.

## Manual Approval Boundary

Manual approval remains outside the Intelligence Layer. The layer may report whether the manual-approval boundary appears intact, but it must not approve trades or create actions that imply approval.

## Failure Handling

The layer must fail closed in interpretation.

Rules:

- missing safety evidence means safety is unknown
- missing feed evidence means feed tradability is unknown
- missing ranking evidence means ranking quality is unknown
- contradictions block strong conclusions
- stale files must not be treated as current truth
- impossible values must invalidate affected conclusions

## Never Infer Safety from Absence of Evidence

Absence of broker-call evidence is not proof that no broker call happened unless the evidence contract explicitly captures that fact.

Two examples:

1. If no order log exists but no broker-call audit artifact exists either, the correct conclusion is insufficient evidence.
2. If audit-only flags are missing from session evidence, the correct conclusion is unknown, not safe.

## Regression Protection Principles

Every future implementation PR must preserve these boundaries:

- no runtime behavior change unless explicitly scoped
- no broker/order imports in read-only intelligence modules
- deterministic tests for new behavior
- no broad refactors
- no fake happy-path-only tests
- no silent fallback hiding broken data
- no weakening of existing evidence or safety contracts

## Scope Violation Rule

Any PR that introduces broker calls, runtime mutation, strategy tuning, ranking threshold changes, feed restarts, or automatic trading actions into the Intelligence Layer must be rejected.
