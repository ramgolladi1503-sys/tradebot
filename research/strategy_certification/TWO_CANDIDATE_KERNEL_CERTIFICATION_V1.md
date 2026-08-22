# Two-Candidate Strategy Certification Kernel Campaign V1

## Authority

- Base authority: `research/strategy-certification-kernel-v0`
- Campaign branch: `research/two-candidate-kernel-certification-v1`
- Research only: `true`
- Runtime authority: `NONE`
- Broker actions permitted: `false`
- Production/live promotion permitted by this campaign: `false`

This campaign applies the existing bounded Strategy Certification Kernel to exactly two pre-existing strategy candidates. It is certification, not discovery.

Kernel lifecycle law remains authoritative:

`Hypothesis Factory -> Candidate Certification Kernel -> Strategy Passport -> MROS -> TradeBot research integration -> shadow/live-forward evidence -> possible runtime promotion`

Legal kernel outcomes are:

- `VALIDATED_RESEARCH`
- `REJECTED`
- `ROBUSTNESS_REQUIRED`

Missing evidence fails closed. A screen PASS cannot substitute for robustness.

## Global anti-overfit law

1. No threshold changes after observing results.
2. No holdout reshuffle.
3. No parameter expansion.
4. No candidate relabeling after failure.
5. No synthetic substitution for missing option/bid/ask/provenance fields.
6. No midpoint or spot-scaled option proxy may be promoted as executable option evidence.
7. Any change to instrument, family, direction, parameters, entry, exit, cost assumption, dataset SHA-256, or information-set ID creates a new candidate identity.
8. An already-accessed holdout cannot be represented as pristine.

---

# Candidate A — HTF_RANGE_EXPANSION

## Current admission status

`PRE_CERTIFICATION_DATASET_BINDING_REQUIRED`

The prior `PROMOTE_TO_PAPER` verdict is historical evidence only. It is not a kernel certification verdict.

## Frozen mechanism

- Underlying: NIFTY
- Family: higher-timeframe range expansion
- Opening Drive: 09:15–10:00, first three completed 15-minute candles
- Bull trigger: completed 15-minute close above Opening Drive high
- Bear trigger: completed 15-minute close below Opening Drive low
- Regime: `VOL_EXPANSION` only
- Structural alignment: breakout direction aligned with trailing 15m and 30m trend
- Legal entry: next 1-minute open after completed trigger candle
- Signal window: 10:15–14:30
- Gap exclusion: reject session if absolute opening gap versus prior close exceeds 0.5%
- Stop: opposite side of Opening Drive, minimum 2 index points
- Target: frozen 1R/2R geometry from Opening Drive risk
- Original time stop: 15:15 EOD
- BUY-only expression: CE bullish / PE bearish

Do not modify this identity during certification.

## Mandatory identity reconciliation gate

Before dataset binding or outcome access, prove the relationship between:

- `HTF_RANGE_EXPANSION`
- `HTF_OPENING_DRIVE_CONT`

Allowed verdicts:

- `SAME_STRATEGY_DIFFERENT_LABEL`
- `RANGE_EXPANSION_IS_CAUSALLY_HARDENED_SUCCESSOR`
- `PARTIAL_OVERLAP`
- `DISTINCT_STRATEGIES`
- `EVIDENCE_CONFLICT_UNRESOLVED`

Compare exact opening-range definition, regime gate, trend alignment, gap exclusion, timestamp semantics, entry, stop, target, time stop, source implementation and replay implementation.

If unresolved, kernel verdict is `ROBUSTNESS_REQUIRED`; do not pool evidence across identities.

## Dataset binding gate

Recover the exact historical source bytes used by the authoritative HTF study. Create a manifest containing:

- source path/vendor reference
- SHA-256
- timezone
- timestamp semantics
- field semantics
- date range
- row count
- session count
- bar interval
- duplicates
- missingness
- exclusions
- provenance lineage

No similar substitute dataset is allowed under the same candidate identity.

Only after exact dataset SHA is known may the immutable candidate-of-record fingerprint be generated.

## Reproduction gate

Run the frozen candidate twice from independent clean output roots. Require identical:

- candidate count
- candidate semantic hash
- trade ledger hash
- metrics

An independent oracle must separately verify Opening Drive construction, completed-bar causality, regime gate, trend alignment, gap exclusion, legal next-1m entry, stop/target/time-stop semantics and session limits.

## Required robustness attack

At minimum:

- chronological OOS
- walk-forward positivity
- realistic friction and 2x friction
- delay sensitivity
- session/month concentration
- top-winner removal
- long/short split
- time-of-day stability
- regime stability
- negative controls
- fallback exclusion
- future-mutation/leakage tests

Negative controls must include matched random entries, direction inversion, delayed entry and event-time perturbation. Gate removals are ablations only; they cannot silently become tuned replacement strategies.

## Option-economic gate

Historical spot-scaled option-equivalent P&L is not executable evidence.

Recover and classify all paper/observation records as:

- `REAL_MARKET`
- `FIXTURE`
- `TEST`
- `SYNTHETIC`
- `STALE`
- `DUPLICATE`
- `UNPROVEN`

Reconcile the known historical contradiction where one daily artifact reports one completed +1.90R signal while a weekly artifact reports zero cumulative/closed signals.

Only `REAL_MARKET` records count toward prospective option evidence.

For executable option economics require decision-time expiry/strike/side plus same-or-prior quote provenance, bid, ask, quote age, spread, buy-at-ask semantics, sell-to-close-at-bid semantics, fees/slippage, duration, MFE/MAE and exit reason.

If real-market option evidence is insufficient, the maximum legal state is not `VALIDATED_RESEARCH`; return `ROBUSTNESS_REQUIRED` with the missing dimension named.

## 30-minute integration mismatch

The original candidate's 15:15 time stop may exceed the current intended <=30-minute TradeBot holding contract.

Do not mutate the original candidate.

Report:

`ORIGINAL_HOLD_CONTRACT_COMPATIBLE_WITH_CURRENT_30M_LIMIT=true|false`

A 30-minute-capped version, if later justified, must be a NEW candidate identity such as `HTF_RANGE_EXPANSION_30M_COMPAT_V1` and cannot inherit pristine holdout status from the parent.

---

# Candidate B — COMMON_FACTOR_OPTION_UNDERREACTION_V1

## Source authority

- Prior branch: `research/common-factor-option-underreaction-v1`
- Prior head: `14507f7e93b08f1dadac3625f687454c18c41643`
- Frozen contract path: `research/common_factor_option_underreaction_v1/research_contract.json`

## Current admission status

`PRIOR_RESULT_AND_HOLDOUT_INTEGRITY_RECOVERY_REQUIRED`

Do not rerun or redesign before recovering prior execution evidence.

## Frozen mechanism

`coherent constituent common-factor shock + broad participation + low concentration + NIFTY lag + same-direction option underreaction -> buy same-direction option next minute`

Direction source remains the sign of the completed constituent median return, frozen before entry/future option prices are read.

Frozen maximum variants: 3.

Frozen execution contract:

- nearest non-expired same-strike ATM CE/PE pair within 100 NIFTY points
- CE for positive common factor, PE for negative common factor
- exact next-minute open entry
- horizons: 5, 10, 15, 20 minutes
- primary friction: 1.0% premium return
- severe friction: 1.5%
- chronological 70/15/15 split
- five expanding OOF folds
- mirror-wing control
- additional one-minute-delay control
- bootstrap/top-winner/concentration gates

No threshold, direction, horizon, pair rule or friction change is legal under this candidate identity.

## Prior-result recovery gate

Search GitHub Actions artifacts, local downloads, archived worktrees, external TradeBotData evidence, and runtime evidence for the original frozen run.

Produce:

- `prior_campaign_executed=true|false|unknown`
- `validation_accessed=true|false|unknown`
- `holdout_accessed=true|false|unknown`
- `final_result_recovered=true|false`
- original run SHA(s)
- original dataset SHA(s)
- final decision artifact hash
- independent audit artifact hash

If holdout access cannot be proven false, set:

`HOLDOUT_INTEGRITY=UNKNOWN`

Never call the holdout pristine in that state.

## Data admission gate

The campaign used a constituent/index common-factor dataset plus expired-option data. Bind exact immutable data identities before a rerun.

For every input require SHA-256, source, path/vendor reference, timezone, timestamp semantics, field semantics, date range, row count, duplicates and missingness.

The option dataset must not gain synthetic bid/ask/IV/OI fields. Historical absence of executable bid/ask/IV remains a declared economic-authority weakness rather than something to impute.

## Exact rerun gate

Only if prior evidence recovery shows rerunning is scientifically legitimate, execute the original frozen campaign byte-for-byte/semantically identically.

Allowed original campaign result taxonomy remains:

- `VALIDATED_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE`
- `COMMON_FACTOR_DIRECTIONAL_EDGE_OPTION_TRANSLATION_FAILED`
- `NO_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE`
- `INSUFFICIENT_COMMON_FACTOR_EVENT_OCCURRENCE`
- `INSUFFICIENT_DIRECTIONAL_OPTION_COVERAGE`
- `DATA_CONTRACT_BLOCKED`
- `INVALID_EVIDENCE_PIPELINE`

These are campaign evidence labels, not final kernel states. Map them through the Strategy Certification Kernel only after independent attack.

## Kernel robustness attack

Require:

- deterministic reproduction
- chronological OOS
- expanding OOF/WFA evidence
- primary and severe friction
- delay control
- mirror-wing control
- matched directional-underlying control
- top-winner removal
- session concentration
- bootstrap uncertainty
- multiple-testing accounting for all three frozen variants/horizons
- fallback exclusion
- future-mutation/leakage tests
- independent audit with no campaign-logic import for key calculations

If the directional underlying effect survives but the option translation does not, the strategy candidate is `REJECTED` for option execution even if its market-information hypothesis is retained separately as research evidence.

Because historical bid/ask were unavailable, do not claim `EXECUTION_VIABLE` or an equivalent executable-option authority from OHLC/LTP-only evidence.

---

# Confidence Passport requirement

Each candidate must end with a confidence passport containing:

- Claim ID/version
- Lifecycle state
- Authority grade
- Observation Authority
- Data Authority
- Information Authority
- Mechanism Authority
- Statistical Authority
- Economic Authority
- Independent Attack
- Known Weaknesses
- Review Trigger
- calibrated confidence only if a valid calibration basis exists; otherwise `UNcalibrated`
- Decision lineage/supersession chain

---

# Final kernel decision rules

For each candidate return exactly one kernel state:

- `VALIDATED_RESEARCH`
- `REJECTED`
- `ROBUSTNESS_REQUIRED`

Then separately report dimension-level authority without upgrading the kernel state:

- implementation/causality
- historical information
- OOS
- WFA
- costs
- negative controls
- concentration
- option translation
- prospective evidence
- execution viability

`VALIDATED_RESEARCH` is still research-only. It does not authorize paper/live/broker execution.

## Terminal report

```text
TWO_CANDIDATE_KERNEL_CERTIFICATION_V1

KERNEL_BASE=
KERNEL_BASE_SHA=
CAMPAIGN_BRANCH=research/two-candidate-kernel-certification-v1
WORKTREE=
WORKTREE_CLEAN=

HTF_IDENTITY_RELATION=
HTF_DATASET_SHA=
HTF_CANDIDATE_FINGERPRINT=
HTF_REPRODUCTION=
HTF_OOS=
HTF_WFA=
HTF_COST_1X=
HTF_COST_2X=
HTF_NEGATIVE_CONTROLS=
HTF_CONCENTRATION=
HTF_OPTION_TRANSLATION=
HTF_PROSPECTIVE_EVIDENCE=
HTF_30M_COMPATIBLE=
HTF_KERNEL_STATE=
HTF_PASSPORT=

COMMON_FACTOR_PRIOR_RESULT_RECOVERED=
COMMON_FACTOR_HOLDOUT_INTEGRITY=
COMMON_FACTOR_DATASET_SHA_SET=
COMMON_FACTOR_CANDIDATE_FINGERPRINT=
COMMON_FACTOR_EXACT_RERUN=
COMMON_FACTOR_OOS=
COMMON_FACTOR_WFA=
COMMON_FACTOR_COSTS=
COMMON_FACTOR_NEGATIVE_CONTROLS=
COMMON_FACTOR_CONCENTRATION=
COMMON_FACTOR_OPTION_TRANSLATION=
COMMON_FACTOR_KERNEL_STATE=
COMMON_FACTOR_PASSPORT=

ANY_VALIDATED_RESEARCH=
STRUCTURAL_EDGE_CERTIFIED=false
RUNTIME_AUTHORITY=NONE
BROKER_ACTIONS=0
NEXT_SINGLE_ACTION=
```

Do not manufacture a PASS. A clean `REJECTED` or `ROBUSTNESS_REQUIRED` result is a successful certification outcome.