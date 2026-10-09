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

## Claim-level evidence gates

Material work items also carry the four claim-level evidence dimensions defined in
[`governance/evidence/POLICY.md`](../../governance/evidence/POLICY.md). These are
named `G1_SOURCE`, `G2_CORRECTNESS`, `G3_ADVERSARIAL`, and `G4_INDEPENDENT` in the
evidence record so they are not confused with delivery lifecycle gates G0-G9.

The existing Product Owner/BA/Architect, Developer, QA/Senior QA, UAT, and
Release Manager roles own these checks. Work-item evidence is recorded in the
existing `core.delivery` contract and hash chain. The report-only CI workflow
validates registry and path coverage but cannot approve a claim or merge. During
migration, missing legacy evidence remains `UNVERIFIED`; `NOT_APPLICABLE` needs
a reason and reference and is not a pass. Developers cannot author their own
independent G2/G3/G4 evidence.

## Runtime-sensitive minimum checks

Use relevant checks from the repository PR template and any targeted tests required by the story.

## Research-specific separation

A green engineering release does not imply:

- certified strategy edge
- profitable trading system
- live-trading authorization
- statistical validity

Research claims require their own evidence and governance.
Profitability and predictive-validity claims remain subject to the separate
research validation and certification controls. A green evidence workflow or
passing unit suite does not establish a trading edge or live readiness.

## Stop conditions

Use explicit states instead of forcing progress:

`BLOCKED_REQUIREMENT`, `BLOCKED_DATA`, `BLOCKED_RESEARCH`, `FAILED_VERIFICATION`, `QA_FAILED`, `UAT_FAILED`, `CI_FAILED`, `RELEASE_BLOCKED`.
