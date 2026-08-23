# Confidence Passport — HTF_RANGE_EXPANSION

## Identity

- Claim ID: `HTF_RANGE_EXPANSION`
- Claim version: historical locked specification
- Lifecycle state: `ROBUSTNESS_REQUIRED`
- Authority grade: `HISTORICAL_EVIDENCE_DISQUALIFIED`
- Passport version: `1`
- Review date: `2026-08-23`
- Runtime authority: `NONE`

## Observation Authority

Historical PR #597 / merge commit `39612d296b07a4800c4f574c8a0dd92c20906e7c` committed a locked strategy specification, the historical `HTFEngine`/`HTFStrategy` implementation, stress reports, scoreboards and the prior `PROMOTE_TO_PAPER` summary.

The committed promotion result cannot be admitted as kernel certification evidence because the historical implementation has material causal and specification-parity defects and the exact original raw source corpus/invocation is not proven.

## Data Authority

`UNPROVEN` for the historical run.

The historical engine accepts an external `data_dir` and concatenates every `*.csv` in that directory. The exact invocation, directory, ordered source set and corpus SHA-256 were not durably recorded and were not recovered from the local provenance sweep.

Therefore no immutable historical dataset binding can be established for the prior +0.47R claim.

## Information Authority

The committed reports claim approximately +0.47R under the gated historical population and 727 `VOL_EXPANSION` trades. That result is not admissible evidence of predictive information because the membership gate itself was computed with future session information.

The historical `HTFEngine` calculates each session's volatility from the full day's maximum high and minimum low, then uses that completed-day quantity to label intraday rows as `VOL_EXPANSION`. A decision earlier in the session can therefore depend on price extremes occurring later in the day.

Information authority is not established.

## Mechanism Authority

The locked specification claims:

- completed 15-minute Opening Drive breakout
- `VOL_EXPANSION` only
- 15m/30m directional alignment
- next-1m legal entry
- gap exclusion
- stop at the opposite Opening Drive boundary with a 2-point minimum

The historical implementation is not byte/semantic faithful to that contract:

1. `VOL_EXPANSION` is future-derived from the full session range.
2. In `BASELINE`, when regime is `VOL_EXPANSION`, the implementation sets both `trend_up` and `trend_dn` true, bypassing the required 15m/30m directional alignment for `RANGE_EXPANSION`.
3. The stop is set to the trigger 15m candle low/high and clamped to a minimum 10-point risk, not the opposite Opening Drive boundary with a 2-point minimum.

Therefore the historical implementation cannot certify the locked mechanism.

## Statistical Authority

Historical scoreboards/stress tables are descriptive only under this passport. They are not accepted as a valid kernel sample because candidate membership is contaminated by future information and exact raw-data provenance is unbound.

No new holdout, OOS or WFA outcome was opened in the current kernel campaign.

## Economic Authority

Not established.

The historical paper-promotion summary uses proxy option economics, while executable real-option provenance remains incomplete. This is secondary to the upstream causal/spec-parity failure.

## Independent Attack

The current kernel attack identified the future-derived regime gate and implementation/spec mismatch directly from the historical source committed with PR #597.

The committed `stress_test_reconciliation.md` explains the old-versus-new friction discrepancy as different populations and cost models, but that reconciliation does not cure the future leak or specification mismatch.

## Known Weaknesses

- exact historical raw corpus/invocation unavailable
- historical result generator lineage incomplete
- future-derived full-session volatility regime
- 15m/30m alignment bypass in `VOL_EXPANSION`
- stop/risk contract mismatch
- executable option evidence incomplete
- original 15:15 time stop may violate the current intended <=30-minute integration contract

## Review Trigger

The historical `PROMOTE_TO_PAPER` result must not be restored as evidence under this identity.

If the mechanism is retained, the legal next step is a **new candidate identity** on a SHA-bound reproducible corpus with:

- causally computed volatility state using only information available by decision time;
- byte-faithful implementation of the declared opening-drive, trend-alignment, entry and risk contract;
- no inheritance of the historical promotion verdict or holdout authority.

## Confidence

`UNcalibrated`.

## Decision Lineage

1. Historical source/PR: `39612d296b07a4800c4f574c8a0dd92c20906e7c` / #597
2. Historical verdict: `PROMOTE_TO_PAPER` — now `DISQUALIFIED_AS_CERTIFICATION_EVIDENCE`
3. Provenance recovery: insufficient exact historical corpus authority
4. Kernel code audit: future leakage + frozen-spec parity failure
5. Current kernel state: `ROBUSTNESS_REQUIRED`

No runtime, broker, paper or production authority is granted.
