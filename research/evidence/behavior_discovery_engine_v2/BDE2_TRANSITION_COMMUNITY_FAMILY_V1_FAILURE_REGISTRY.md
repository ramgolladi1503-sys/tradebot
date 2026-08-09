# BDE2 Transition Community Family V1 — Failure Registry

Verdict: `DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_NO_SURVIVOR`

## Scope

- Engine: `BEHAVIOR_DISCOVERY_ENGINE_V2`
- Family: `BDE2_TRANSITION_COMMUNITY_FAMILY_V1`
- Runner: `BEHAVIOR_TRANSITION_COMMUNITY_DEVELOPMENT_OUTCOME_V1`
- Instrument: `NIFTY`
- Dataset SHA: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- Episodes SHA: `3e84238a1530aa3896dcfd45c96b76ab0ab1e647968e21c514361e2e280cd8f5`
- Candidate SHA: `ab62236a13cd041aff7bde8dc264428f8648b8e93a5c833734b21f1ab3db5879`
- Sessions total: `493`
- Development sessions: `394`
- Locked sessions: `99`
- Locked outcomes accessed: `false`
- Forward outcomes scope: `development_sessions_only`

## Discovery pressure

- Transition communities read: `13`
- Selected candidates: `4`
- Rejected pre-outcome candidates: `9`
- Development-supported candidates: `0`

## Development result

All selected high-information transition-community candidates were rejected in development.

Rejected centers:

- `UPSIDE_ESCAPE`
- `DOWNSIDE_ESCAPE`
- `FAILED_UPSIDE_ESCAPE`
- `FAILED_DOWNSIDE_ESCAPE`

Primary rejection modes included:

- insufficient ret6 median magnitude;
- insufficient ret12 median magnitude for most candidates;
- ret6/ret12 sign inconsistency for `FAILED_DOWNSIDE_ESCAPE`;
- no inferred direction.

## Governance consequence

Do not run locked/OOS validation for this family.

Do not rescue this family by weakening development gates or retuning the transition-community selector after seeing the development result.

Materially new work must use a different representation or information class, such as:
- fixed pre-outcome time-of-day/session-position stratification;
- episode shape/velocity features not equivalent to transition communities;
- breadth/constituent/index lead-lag;
- options/futures microstructure;
- depth/liquidity/volatility surface evidence.

## Controlled verdict

`NO_DEVELOPMENT_SUPPORTED_TRANSITION_COMMUNITY_CANDIDATE`
