# MROS Sprint-002 — Certifier Calibration Charter

## Program Position

- Milestone: M2 — Certifier Calibration
- Work Package: WP-003
- Sprint: Sprint-002
- Parent governance branch: `research/mros-governance-sprint-001`
- Objective: determine whether the existing research certifier has measured and scientifically defensible operating characteristics.

## Frozen Objective

Calibrate the certifier itself. Do not discover strategies, rescue rejected hypotheses, relax PR #806 thresholds, inspect sealed unopened data, modify runtime, or authorize paper/live execution.

## Exit Criterion

A quantified calibration report must exist with registered evidence for:

1. synthetic edge recovery across effect sizes;
2. null-world false-positive behavior;
3. power / false-negative behavior;
4. representation sensitivity;
5. multiplicity sensitivity;
6. semantic alignment between the tested statistical null and the economic claim;
7. explicit applicable and invalid operating regions;
8. independent attack and reproduction status.

Sprint-002 may end with `CERTIFIER_NOT_CALIBRATED` or a narrowly scoped calibration authority. A favorable verdict is not required.

## Existing Evidence to Audit, Not Trust Automatically

Repository branch `audit/pr806-certifier-calibration-v1-final` contains an existing reverse-certification lane for PR #806. Its report states that the frozen certifier recovered large planted effects, showed strong diagnostic null-world false-positive control, but was materially underpowered for sparse modest effects and used sign-test semantics narrower than positive expectancy.

That work is input evidence only. MROS must independently verify its code, frozen inputs, outputs, hashes, calibration design, and reproducibility before promotion into the Calibration Registry.

## No-Rescue Rule

The 12 PR #806 hypotheses reported as satisfying all non-BH Stage-6 gates remain rejected by the frozen campaign. Calibration evidence may narrow what the negative campaign means; it may not promote near misses or reopen consumed hypotheses.

## Required Sprint-002 Deliverables

- calibration target specification;
- audit of existing PR #806 calibration implementation;
- registered Calibration ID, Experiment IDs, Dataset/Input IDs, and Evidence IDs;
- independent reproduction evidence;
- null-world and planted-edge results;
- power curve / detectable-effect interpretation;
- representation and multiplicity audit;
- statistical-target semantic audit;
- independent attack report;
- quantified final calibration authority report.

## Stop Conditions Requiring Human Attention

Stop and request human attention only if a required artifact cannot be obtained from repository/GitHub evidence, a sealed-data boundary would need to be crossed, credentials/private data are required, an architecture change outside M2 becomes necessary, or a merge/operational authorization is required.
