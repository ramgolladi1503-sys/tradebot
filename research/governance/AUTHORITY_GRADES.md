# Authority Grades — MROS v1.0

Authority: MROS Enterprise Engineering Manual & Research Handbook v1.0, adopted by `DEC-2026-0001`.

Authority grades apply to a specific claim and scope. They do not describe the prestige of an agent, branch, report, or project.

## Research / R

Exploratory or incomplete. Cannot influence runtime or capital.

Typical examples:

- a registered hypothesis with incomplete testing;
- a reproducible calibration observation that has not completed the applicable MROS work package.

## Grade C

Reproducible observation with material unresolved assumptions.

Minimum interpretation:

- provenance and procedure are reproducible;
- the observation is real within the stated dataset/procedure;
- material assumptions, representation limits, replication gaps, calibration gaps, or mechanism uncertainty remain.

Grade C must not be described as a certified market edge.

## Grade B

Replicated supported claim with calibrated statistical authority; not necessarily economically executable.

Minimum interpretation:

- independent or meaningfully distinct replication supports the claim;
- applicable statistical/certifier procedures are calibrated within the claim's tested domain;
- multiplicity, leakage, representation, and uncertainty requirements applicable to the claim have been addressed;
- unresolved defects do not contradict the Grade B statement.

Grade B grants no runtime or capital authority by itself.

## Grade A

Scientific and economic certification passed, independent attack survived, and limitations are explicit.

Minimum interpretation:

- applicable scientific-certification gates passed;
- economic certification passed under the stated execution/cost/capacity assumptions;
- independent attack was completed and no unresolved Critical/High blocker remains;
- limitations, destroyers, review triggers, and expiry conditions are explicit.

Operational integration still requires the M9 governed integration boundary.

## Grade A+

Grade A plus live/forward evidence across required regimes and continuing monitoring; still subject to expiry and review triggers.

Grade A+ is not permanent authority. Material drift, data changes, implementation changes, failed monitoring, or contradictory evidence can downgrade it.

## Rejected

Evidence contradicts the claim or required gates fail.

Rejected claims remain queryable and keep their evidence/decision lineage. Rejection is a valid research outcome, not missing work.

## Unknown

Evidence is insufficient to support or reject the claim.

Unknown must be used when data, calibration, representation, sample size, implementation, or other authority is inadequate for a defensible verdict. It must not be converted to Rejected merely to create closure.

## Mandatory Rules

- Scientific grade is one of: `Research / R`, `Grade C`, `Grade B`, `Grade A`, `Grade A+`, `Rejected`, `Unknown`.
- No discovering agent may assign final authority to its own discovery without the required independent review and decision path.
- Promotion requires explicit gate evidence and a recorded decision.
- Exceptions cannot grant higher authority than the underlying evidence supports.
- The weakest applicable unresolved authority dimension bounds the final grade.
- Runtime and capital cannot consume `Research / R`, `Grade C`, `Grade B`, `Rejected`, or `Unknown` as operational authority.
- Grade A/A+ still require M9 compatibility, version, expiry, and runtime integration controls before TradeBot consumption.
- Failed reproduction, contradictory evidence, calibration failure, representation failure, economic failure, or implementation mismatch may immediately reduce authority.

The former bootstrap `A0–A5` scale is superseded by this manual-defined scale and must not be used for new MROS records.
