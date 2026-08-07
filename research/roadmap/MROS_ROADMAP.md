# MROS Roadmap — Program Baseline v1.0

Authority: MROS Enterprise Engineering Manual & Research Handbook v1.0, repository-adopted under DEC-2026-0001.

Program size: 9 milestones, 24 work packages, 120 controlled sprints, five sprints per work package.

The uploaded controlled manual is the governing program baseline. The source PDF is identified by SHA-256 `53350c3f60f2046180726077b0c18fb52222d6826d4d6e10fc746a46ab80cb39` and size `4,238,440` bytes. This roadmap is the repository representation of its program structure; changes to milestone intent, work-package intent, authority grades, or gate semantics require a recorded decision and impact review.

## Execution law

- Execute milestones and work packages in dependency order.
- Each work package has exactly five controlled sprints: contract/design freeze, core implementation, integration/negative controls, verification/independent attack, acceptance/evidence seal/handoff.
- A green CI run is necessary but not sufficient for acceptance.
- Every sprint must produce repository artifacts and evidence.
- Adjacent ideas go to the Parking Lot; no silent scope expansion.
- No discovering agent may grant final authority to its own result.
- Calibration precedes strong interpretation of negative certification verdicts.
- Runtime consumes certified knowledge and does not conduct research.

## M1 — Research Governance

Work packages:

- WP001 Research Constitution
- WP002 Governance & Authority Model
- WP003 Research Registries & Identity
- WP004 Decision Ledger & Supersession
- WP005 Research Knowledge Graph
- WP006 MROS Bible & Research Journal

Controlled sprints: S001–S030.

Milestone acceptance: every future research artifact can be produced and reviewed without tribal knowledge; governance schemas and templates are executable and independently understandable.

Exit gate: all included WPs accepted; no unresolved Critical/High research-integrity defects; evidence manifest sealed; manual and journal updated.

### Current state

The existing `research/mros-governance-sprint-001` work is treated as a bootstrap corpus containing reusable artifacts across several M1 work packages. It does **not** by itself prove acceptance of WP001–WP006 or S001–S030. Existing artifacts must be mapped to the controlled sprint acceptance criteria, gaps implemented, negative controls run, independent attack completed, and evidence sealed.

## M2 — Certifier Calibration

Work packages:

- WP007 Certifier Calibration Framework
- WP008 Synthetic Edge Generator
- WP009 Null World Generator
- WP010 Representation Audit
- WP011 Gate Attribution
- WP012 Statistical Power & Multiplicity

Controlled sprints: S031–S060.

Milestone acceptance: a reproducible calibration dossier quantifies false positives, false negatives, detectable effect sizes, multiplicity burden, representation limits, and conditions under which verdicts are invalid.

Exit statement must be exactly one of:

- `CERTIFIER_CALIBRATED_WITHIN_DOMAIN`
- `CERTIFIER_REQUIRES_REDESIGN`

The existing PR #812 calibration work is retained as provisional evidence and implementation material, but progression through M2 is paused until M1 is accepted or a recorded dependency decision proves a specific activity independent without weakening authority.

## M3 — Information Discovery Engine

- WP013 Information Discovery Engine Core
- WP014 Signal Registry & Feature Authority
- WP015 Information Graph & Lead/Lag

Controlled sprints: S061–S075.

Goal: measure predictive information before strategy construction, with causal-time-safe alignment, chronological validation, incremental information analysis, stability, decay, and uncertainty.

## M4 — Mechanism Discovery Engine

- WP016 Mechanism Discovery Engine Core
- WP017 Mechanism Registry & Market Process Graph

Controlled sprints: S076–S085.

Goal: translate high-information relationships into explicit market-process explanations and falsifiable predictions while separating economic mechanism from surface pattern.

## M5 — Hypothesis Factory

- WP018 Hypothesis Factory
- WP019 Hypothesis Scheduler & Search Budget

Controlled sprints: S086–S095.

Goal: generate bounded, predeclared, outcome-blind hypotheses from registered information and mechanisms while preserving search budgets and multiplicity denominators.

## M6 — Scientific Certification

- WP020 Scientific Certification Engine

Controlled sprints: S096–S100.

Goal: certify or reject claims using calibrated statistical methods, chronological replication, robustness attacks, negative controls, independent review, and sealed-holdout discipline.

## M7 — Economic Certification

- WP021 Economic Certification Engine

Controlled sprints: S101–S105.

Goal: separate predictive authority from executable economic authority using bid/ask execution where available, conservative slippage, fees, latency, capacity, market impact, and cost sensitivity.

## M8 — Knowledge Registry

- WP022 Knowledge Promotion & Confidence Passport

Controlled sprints: S106–S110.

Goal: promote only certified outputs into durable institutional knowledge with complete provenance, limitations, review triggers, expiry, and supersession history.

## M9 — Runtime Integration

- WP023 Runtime Integration Gateway
- WP024 TradeBot Certified-Knowledge Consumer

Controlled sprints: S111–S120.

Goal: expose only versioned certified knowledge to TradeBot through a governed read-only integration boundary. Runtime cannot manufacture confidence, reinterpret research authority, or silently promote research outputs.

## No-drift rule

Every active sprint has one objective and one exit criterion. Any architecture change requires: stop, evidence, reasoning, recorded decision/impact review, roadmap update, then continuation. Unknown and rejected outcomes are valid institutional results.
