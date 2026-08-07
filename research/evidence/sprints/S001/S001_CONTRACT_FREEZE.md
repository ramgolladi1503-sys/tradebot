# S001 — WP001 Contract / Design Freeze Evidence

Sprint: S001
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Branch: `research/mros-program-v1`
Primary implementation commit: `3770e57454c4fae2cacefafb6073909356e37229`
Status: IMPLEMENTED_FOR_REVIEW — NOT YET ACCEPTED
Authority Grade: Research / R

## Sprint Objective

Freeze the Research Constitution contract against MROS Enterprise Engineering Manual v1.0 before expanding implementation.

## Frozen Product Contract

The constitution must define, without relying on conversational context:

- mission and repository authority;
- four primary knowledge classes: Observed Fact, Inference, Hypothesis, Speculation;
- Unknown and Rejected as legal verdicts;
- RC-001 through RC-010;
- burden of proof;
- evidence-only promotion;
- independent attack;
- causal-time safety;
- denominator/search-budget preservation;
- runtime/research separation;
- reproducibility and completion-language rules;
- formal change control.

## WP001 Acceptance Tests Frozen for Later Sprints

WP001 cannot be accepted unless the following are demonstrated with repository evidence:

1. The Constitution can be applied to at least three historical TradeBot/MROS examples without ambiguity.
2. No constitutional rule or lifecycle path permits authority promotion without new evidence.
3. An independent reviewer/session can classify a frozen set of sample statements consistently into the knowledge classes/verdicts.
4. Negative tests demonstrate that ambiguous, unsupported, future-contaminated, denominator-resetting, self-certified, and runtime-invented authority fail closed.
5. No Critical/High constitution ambiguity or conflict remains.
6. Required artifacts, commands, hashes, decisions, assumptions, unknowns, and attack notes are sealed at WP acceptance.

## Explicit Non-Goals

S001 does not:

- certify any market claim;
- calibrate a certifier;
- implement strategy discovery;
- touch TradeBot runtime, broker, risk, UI, MEG, TrueData, ML, or indicators;
- declare WP001 complete;
- declare M1 complete.

## Known Bootstrap Conflicts Identified

### Conflict 1 — Authority grades

The bootstrap repository used `A0–A5`. The adopted manual defines `Research / R`, `Grade C`, `Grade B`, `Grade A`, `Grade A+`, `Rejected`, and `Unknown`.

Resolution: bootstrap authority scale superseded on the program branch by the manual-defined scale.

### Conflict 2 — Program shape

The bootstrap roadmap used 5 milestones / 9 WPs. The adopted manual defines 9 milestones / 24 WPs / 120 sprints.

Resolution: corrected by `DEC-2026-0001` and the v1.0 roadmap.

### Conflict 3 — PR-per-sprint execution assumption

Early bootstrap work created separate sprint PRs. The program now uses one persistent integration branch with sprint commits/evidence and milestone CI gates.

Resolution: `DEC-2026-0002`; PRs #811 and #812 closed unmerged as superseded execution vehicles.

## Required Next Sprint

S002 — implement the frozen Constitution contract in forms that can be deterministically checked, including controlled statement-classification and rule-validation fixtures. S002 must not weaken or expand the frozen contract silently.

## Observed Facts

The manual defines the WP001 product as a versioned constitution controlling what may be claimed and requires the three core WP acceptance properties listed above.

## Inferences

The original bootstrap Constitution was directionally aligned but insufficiently canonical because it did not explicitly encode RC-001–RC-010 or the manual-defined knowledge/authority semantics.

## Hypotheses

A deterministic classifier/validation fixture can expose constitutional ambiguity before later MROS work depends on it.

## Assumptions

The repository-adopted manual v1.0 remains the governing baseline.

## Destroyers

- a constitutional rule permitting evidence-free promotion;
- conflicting definitions that allow the same frozen statement to receive incompatible classes without an explicit ambiguity outcome;
- later hidden changes to RC-001–RC-010 without a decision record.

## Unknowns

Independent classification consistency has not yet been measured. Historical-example application has not yet been executed. Therefore S001 is not accepted yet.

## Next Experiment

Implement the S002 deterministic rule/classification fixtures and negative controls against this frozen contract.

## Authority Grade

Research / R.
