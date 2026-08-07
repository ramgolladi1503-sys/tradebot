# MROS Research Constitution

Version: 1.0
Status: FROZEN CONTRACT FOR WP001 VERIFICATION
Manual authority: MROS Enterprise Engineering Manual & Research Handbook v1.0
Program decision authority: `DEC-2026-0001`, `DEC-2026-0002`
Operational authority: NONE

## 1. Mission

MROS exists to maximize the probability that accepted market claims are objectively defensible within explicitly stated assumptions. TradeBot is one downstream consumer. The research organization is the primary system.

The Constitution governs what MROS may claim. It does not guarantee that markets contain a profitable edge, that a strategy will be discovered, or that trading will be profitable.

## 2. Knowledge Classes

Every material research statement must be classifiable as exactly one primary knowledge class at the point it is recorded.

### Observed Fact

Directly supported by reproducible evidence without interpretive extension.

Example: `The frozen Stage-6 artifact contains 648 hypothesis result rows.`

### Inference

Best current explanation of observed evidence; alternatives remain possible.

Example: `The tested certifier appears underpowered for modest sparse effects under the tested representation.`

### Hypothesis

A falsifiable mechanism or prediction that has not earned sufficient evidence.

Example: `Constituent breadth expansion precedes index continuation over a declared horizon.`

### Speculation

An idea worth exploring but not yet supported enough to influence decisions.

Example: `Dealer hedging may explain an observed expiry-day pattern before any mechanism evidence exists.`

`Unknown` is a legal verdict when evidence is insufficient to support or reject a claim. `Rejected` is a legal verdict when evidence contradicts the claim or required gates fail.

## 3. Constitutional Rules

### RC-001 — No Drift

One active sprint objective. Adjacent ideas are parked, not implemented. A material scope change requires a recorded decision and impact review before work continues.

### RC-002 — Evidence Promotion

Authority can increase only when new registered evidence satisfies predeclared gates. Reformatting, rerunning the same evidence without a scientific reason, model confidence, human confidence, green CI alone, or persuasive prose are not new evidence.

### RC-003 — Unknown Is Legal

MROS may conclude `UNKNOWN` or `INSUFFICIENT EVIDENCE` without penalty. Unknown must not be converted to rejection merely to create closure, and it must not be converted to support merely because a result is promising.

### RC-004 — Independent Attack

Discovering agents do not grant final authority to their own claims. Applicable promotion requires independent review/attack under the authority model. Independence must be substantive, not the same reasoning paraphrased.

### RC-005 — Calibration Before Trust

Research instruments, certifiers, gates, and measurement procedures used for strong verdicts must demonstrate applicable operating characteristics before those verdicts are trusted. A negative certifier result is bounded by demonstrated detection power and representation coverage.

### RC-006 — No Silent Supersession

Changed beliefs are recorded through versioning and explicit supersession. Prior claims, evidence, decisions, and rejection history remain queryable. History is not rewritten to make later conclusions appear inevitable.

### RC-007 — Falsifiability

Every material claim lists destroyers and re-evaluation/review triggers appropriate to its lifecycle state. Claims that cannot state what evidence would weaken or destroy them cannot be promoted as scientific claims.

### RC-008 — Causal Time

Predictors and experimental inputs may use only information genuinely available at the declared decision timestamp. Look-ahead, future-derived membership, future labels in predictors, and outcome-contaminated feature selection invalidate affected evidence until repaired and rerun.

### RC-009 — No Denominator Laundering

Failed hypotheses remain counted. Search budgets, multiplicity denominators, or campaign identities cannot be reset merely because a campaign failed. A new denominator requires new information authority and a recorded decision explaining why the new search family is scientifically distinct.

### RC-010 — Runtime Separation

Runtime may consume versioned certified knowledge through the governed integration boundary but may not invent, reinterpret, promote, or weaken research authority. Runtime output cannot retroactively establish research truth.

## 4. Burden of Proof

The claimant carries the burden of proof. Absence of disproof is not evidence of truth. Statistical significance alone, economic plausibility alone, a profitable backtest alone, high win rate alone, agent confidence alone, or runtime output alone cannot satisfy the burden for certification.

Promotion must follow the governed lifecycle and authority model. No level may be skipped.

## 5. Repository Authority

Repository-backed, identified, versioned evidence is authoritative. Conversation memory, chat summaries, agent scratchpads, dashboards, and uncommitted outputs may assist navigation but cannot override repository state.

Every material research object must receive its required canonical identity when the applicable registry work package is accepted. Anonymous evidence is inadmissible for promotion.

## 6. Reproducibility

Evidence intended to change authority must identify inputs, code/procedure, parameters, time boundaries, transformations, seeds where applicable, outputs, environment assumptions, and relevant hashes/commit IDs sufficiently for an independent session to reproduce the principal result.

Failure to reproduce is evidence and must be recorded.

## 7. Separation of Observation and Interpretation

Research reports must distinguish at minimum:

- Observed Facts
- Inferences
- Hypotheses
- Assumptions
- Destroyers
- Unknowns
- Next Experiment / Review Trigger
- Authority Grade

An inference may not be rewritten as an observed fact. A pattern may not silently become a mechanism claim.

## 8. Promotion and Authority

Scientific grades are governed by the manual-defined scale in `research/governance/AUTHORITY_GRADES.md`:

`Research / R`, `Grade C`, `Grade B`, `Grade A`, `Grade A+`, `Rejected`, `Unknown`.

Promotion requires new evidence, applicable gate evidence, and a recorded decision. No discovering agent can self-certify.

## 9. Negative Results

Null results, rejected claims, invalidated experiments, failed reproductions, destroyed hypotheses, and inadequate-data outcomes are first-class institutional knowledge. They remain traceable and must not be deleted merely because they are inconvenient.

## 10. Completion Language

No artifact may claim completion, calibration, certification, implementation, discovery, milestone pass, work-package pass, or sprint acceptance unless repository evidence demonstrates that exact statement under the applicable Definition of Done.

`Implemented` without evidence is not `Done`.

## 11. Change Control

Changes to constitutional rules, milestone intent, work-package intent, authority grades, or gate semantics require:

1. stop the affected progression;
2. present evidence and reason for change;
3. record a decision and impact review;
4. update controlled program artifacts;
5. continue only from the resulting repository state.

## 12. WP001 Verification Boundary

This document is the frozen WP001 contract. Its existence does not complete WP001. WP001 requires all five controlled sprints, acceptance against the manual criteria, independent review/reproduction, a sealed evidence manifest, and no unresolved Critical/High research-integrity defect.
