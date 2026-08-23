# Confidence Passport — COMMON_FACTOR_OPTION_UNDERREACTION_V1

## Identity

- Claim ID: `COMMON_FACTOR_OPTION_UNDERREACTION_V1`
- Claim version: `V1`
- Lifecycle state: `REJECTED`
- Authority grade: `RESEARCH_REJECTION_AUTHORITY`
- Passport version: `1`
- Review date: `2026-08-23`
- Runtime authority: `NONE`

## Observation Authority

The authoritative GitHub Actions run is `30554186651` (`common-factor-option-underreaction-v1`, run #1) at source head `14507f7e93b08f1dadac3625f687454c18c41643`. The run completed successfully, executed focused tests, the frozen campaign, an independent audit, evidence hashing, and uploaded artifact `8764132399` with digest `sha256:d87c4a4cb61b86ca173cf7877c3c4b64e851fdb5f0e4d6579cb353f24473d57e`.

The recovered final decision is `NO_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE`, with `oof_survivors=0`, `validation_opened=false`, and `holdout_opened=false`.

## Data Authority

Frozen source identities recovered from the CI artifact and Git LFS authority:

- constituent/index corpus SHA-256: `ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0`
- expired-option contract inventory SHA-256: `0c65627990d2ef3aaf59e3cc487381bb3103337caccaf338a80a4fed48c66530`
- data-contract semantic SHA-256: `1e92a382a6dacbc31357c3dab7842f7afbc8ce186e7e71335362e5468cb7ffe6`
- causal option-pair states: `8188` across `160` sessions
- chronological split: research `112`, validation `24`, holdout `24` sessions

Historical bid/ask and IV are unavailable. That limitation did not need to be resolved because the candidate family failed before validation/holdout.

## Information Authority

No frozen variant demonstrated admissible OOF information. All three variants failed the predeclared OOF gate.

Notable failures include negative bootstrap lower bounds, failed top-five-winner removal, inadequate fold positivity, insufficient sample size and/or severe session/winner concentration. The broad/low-concentration variant had 215 OOF trades but negative mean return and profit factor below 1.

Therefore the information claim is rejected before forward partitions are opened.

## Mechanism Authority

The proposed mechanism—constituent common-factor shock leading NIFTY and an underreacting same-direction option wing—was causally specified, but the frozen empirical screen did not establish robust incremental information. Mechanism authority is therefore not established.

## Statistical Authority

- frozen variants: `3`
- frozen horizons: `5,10,15,20` minutes
- campaign-wide tests: `12`
- expanding OOF folds: up to `5`
- OOF survivors: `0`
- validation opened: `false`
- holdout opened: `false`

Because the screen failed, bounded-kernel law makes rejection terminal. Validation and holdout are not required to reject a candidate that fails the frozen upstream gate.

## Economic Authority

No economic/live authority is granted. Historical bid/ask is unavailable and no spread-certified execution claim is made. The strategy did not survive far enough for that limitation to become the deciding gate.

## Independent Attack

Recovered independent audit verdict: `PASS_INDEPENDENT_AUDIT`.

Audit artifact SHA-256: `3c6adc09cd20cd1059ccad495eee8a9aa9771acd7fbff63ce0a8c7ba254b3d23`.

The independent audit reports no failures and does not import campaign logic for its audit path.

## Known Weaknesses

- historical bid/ask unavailable
- historical IV unavailable
- only 160 causal-state sessions available

These weaknesses do not soften the rejection because the family already failed the OOF screen.

## Review Trigger

`REJECTED` is terminal under the current identity. Reopening requires a genuinely new information-set ID, not nearby threshold changes, horizon changes, relabeling, or holdout reshuffling.

## Confidence

`UNcalibrated`.

## Decision Lineage

1. Frozen source head `14507f7e93b08f1dadac3625f687454c18c41643`
2. Actions run `30554186651`
3. Artifact `8764132399`
4. Final decision SHA-256 `19c2b07273256caba24cc29d58c0c425aef20ea946de6c63f0cde528e22bbe1b`
5. Kernel adjudication: `REJECTED`

No broker action, runtime promotion, paper authorization, or production registration is allowed.
