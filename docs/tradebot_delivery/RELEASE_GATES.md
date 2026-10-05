# TradeBot Release Gates

## Release principles

- No direct production merge from development.
- No merge with required red gates.
- No test weakening to make CI green.
- No unresolved required review conversations.
- No undocumented runtime-sensitive change.
- No hidden broker/risk/feed behavior change.

## Required gates

Applicable work must pass:

### G0 Requirement gate
Work item satisfies Definition of Ready and has acceptance criteria.

### G1 Architecture gate
Interfaces, reuse, risks, and high-risk paths are reviewed.

### G2 Development gate
Implementation complete; developer tests pass.

### G3 QA gate
Adversarial QA passes after all defect/fix/retest loops.

### G4 UAT gate
Business behavior and acceptance criteria pass.

### G5 Product gate
Product Owner accepts the work item.

### G6 CI gate
Required automated checks are green.

### G7 Release gate
PR body, evidence, rollback/limitations, and release notes are complete.

### G8 Merge gate
Release Manager marks `MERGE_APPROVED`.

### G9 Production verification gate
Post-merge/runtime verification passes where applicable.

## Runtime-sensitive minimum checks

Use relevant checks from the repository PR template and any targeted tests required by the story.

## Research-specific separation

A green engineering release does not imply:

- certified strategy edge
- profitable trading system
- live-trading authorization
- statistical validity

Research claims require their own evidence and governance.

## Stop conditions

Use explicit states instead of forcing progress:

`BLOCKED_REQUIREMENT`, `BLOCKED_DATA`, `BLOCKED_RESEARCH`, `FAILED_VERIFICATION`, `QA_FAILED`, `UAT_FAILED`, `CI_FAILED`, `RELEASE_BLOCKED`.
