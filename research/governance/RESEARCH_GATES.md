# Research Gates

Gates are blocking controls. Passing one gate does not imply passing another.

## G0 — Registration

Claim, experiment, dataset, and evidence records have IDs, versions, owners, provenance, and declared scope.

## G1 — Data Authority

Dataset provenance, coverage, exclusions, timestamps, transformations, survivorship assumptions, missingness, and integrity checks are documented. Material data defects block further authority.

## G2 — Experiment Integrity

The experiment is reproducible, time-causal where required, leakage-controlled, parameter/search space declared, and outcome computation independently checkable.

## G3 — Statistical Validity

Uncertainty is quantified; multiplicity and selection effects are addressed; appropriate nulls exist; sample size and power are considered; conclusions match the statistical design.

## G4 — Representation Robustness

The result is not an artifact of one arbitrary representation, sampling convention, labeling rule, or transformation unless the claim is explicitly limited to it.

## G5 — Information Stability

Predictive information, when claimed, is measured beyond a single tuned rule and tested for temporal/segment stability and degradation.

## G6 — Mechanism Authority

Mechanism claims require evidence discriminating the proposed mechanism from plausible alternatives. Pattern evidence alone cannot pass this gate for a causal claim.

## G7 — Independent Attack

A documented attack attempts to destroy the claim across data, leakage, multiplicity, representation, robustness, mechanism, and alternative explanations. Unresolved critical attacks block certification.

## G8 — Certifier Calibration

Any certification procedure used has applicable calibration evidence from synthetic edges, null worlds, power analysis, false-positive/negative analysis, representation audit, and multiplicity audit.

## G9 — Economic Certification

Expected edge remains meaningful after realistic costs, slippage, liquidity, capacity, timing, and execution constraints within the claim's scope.

## G10 — Operational Equivalence

The operational implementation consumes equivalent information, timing, transforms, and decision logic to the certified research implementation, with review triggers and guardrails.

## Sprint-001 Boundary

Sprint-001 defines these gates but does not claim that G1-G10 have been empirically calibrated or passed. Calibration belongs to later work packages.
