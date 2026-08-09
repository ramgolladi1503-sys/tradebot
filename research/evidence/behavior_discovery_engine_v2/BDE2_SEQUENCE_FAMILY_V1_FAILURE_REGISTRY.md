# BDE2 Sequence Family V1 — Failure Registry

Verdict: `DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_NO_SURVIVOR`

## Scope

- Engine: `BEHAVIOR_DISCOVERY_ENGINE_V2`
- Family: `BDE2_SEQUENCE_FAMILY_V1`
- Instrument: `NIFTY`
- Dataset SHA: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- Sessions total: `493`
- Development sessions: `394`
- Locked sessions: `99`
- Locked outcomes accessed: `false`
- Forward outcomes scope: `development_sessions_only`

## Discovery pressure

- Episodes scanned: `912`
- Raw recurrent sequences after structural gates: `1709`
- Selected candidates: `25`
- Passports frozen: `25`
- Development-supported candidates: `0`

## Result

All selected frozen BDE2 sequence candidates were rejected in development.

Primary rejection modes included:

- ret6/ret12 sign inconsistency;
- insufficient median ret6 or ret12 magnitude;
- no inferred direction;
- insufficient favorable-vs-adverse excursion asymmetry.

## Governance consequence

Do not run locked/OOS validation for this family.

Do not rescue this family by relaxing development gates or retuning selector thresholds after seeing the development result.

Materially new work must introduce a genuinely different representation, such as:
- morphology clustering with non-outcome features;
- episode-level shape features;
- transition graph/community structure;
- time-of-day/session-position stratification fixed before outcomes;
- a new information class outside this OHLC sequence family.

## Controlled verdict

`NO_DEVELOPMENT_SUPPORTED_BEHAVIOR_SEQUENCE_CANDIDATE`
