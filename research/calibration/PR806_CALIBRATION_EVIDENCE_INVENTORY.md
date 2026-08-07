# PR #806 Calibration Evidence Inventory

## Status

`PROVISIONAL_INPUT — NOT YET MROS-CALIBRATED`

This inventory records existing repository evidence without promoting its conclusions.

## Frozen Campaign Authority

PR #806 is an open draft research PR whose stated terminal result is zero certified structural-edge survivors across 648 frozen hypotheses and whose sealed unopened sessions were not scored. Its own authority explicitly does not claim that all possible strategies or future edges are impossible.

## Existing Reverse-Certification Branch

Branch: `audit/pr806-certifier-calibration-v1-final`

Compared with `research/autonomous-structural-edge-exhaustion-v1`, the branch is seven commits ahead and adds:

- `.github/workflows/pr806-certifier-calibration-v1.yml`
- `docs/agent_reviews/pr806_certifier_calibration_v1.md`
- `docs/research/pr806_certifier_calibration_v1/INITIAL_CALIBRATION_AUTHORITY.md`
- `research/pr806_certifier_calibration_v1/__init__.py`
- `research/pr806_certifier_calibration_v1/calibration.py`
- `scripts/audit_pr806_certifier_calibration_v1.py`
- `tests/test_pr806_certifier_calibration_v1.py`

## Reported Calibration Observations Requiring Reproduction

The existing authority report states:

- all non-BH Stage-6 gates simultaneously: 12 / 648;
- campaign-wide BH q <= 2.5%: 0 / 648;
- dense planted-edge recall: 0.0% at +2 bps, 31.9% at +5 bps, 81.0% at +8 bps, 99.4% at +15 bps;
- sparse planted-edge mean recall: 0.0% at +2 bps, 3.83% at +5 bps, 41.0% at +8 bps, 91.97% at +15 bps;
- 1,000 diagnostic null worlds produced 16 worlds with any BH pass, 19 total BH passes, and one full Stage-6 false positive;
- a positive-mean / low-hit-rate synthetic control is rejected by the current sign-test semantics even though its mean is positive;
- replacing the sign-test input diagnostically with a mean-targeting bootstrap still reportedly produced zero BH survivors on the consumed PR #806 corpus;
- representation/data-authority weaknesses remain unresolved.

These are observations claimed by an existing repository artifact. They are not yet accepted as MROS calibration evidence until independently reproduced and registered.

## Required Verification

1. Verify the calibration implementation actually calls frozen Stage-6/7/8 semantics rather than a simplified substitute.
2. Verify no Stage-9 unopened data are loaded or scored.
3. Verify planted-edge construction does not leak target outcomes into selection beyond the declared synthetic intervention.
4. Verify sparse-trial selection and deterministic seeds.
5. Verify BH denominator remains 648 where claimed.
6. Verify null worlds preserve the intended dependence structure and understand what dependence structures they do not cover.
7. Verify reported recall/FPR calculations from raw outputs.
8. Reproduce the floating-point boundary defect at the +5 bps robustness lane and classify its impact.
9. Audit whether the sign-test target is scientifically compatible with claims the certifier was used to reject.
10. Test representation and multiplicity sensitivity beyond the single frozen configuration before any broad calibration authority is granted.

## Current MROS Interpretation

The existing report is credible enough to justify a focused independent reproduction, but not strong enough to be adopted by assertion. Current MROS authority remains `UNCALIBRATED / PROVISIONAL INPUT`.
