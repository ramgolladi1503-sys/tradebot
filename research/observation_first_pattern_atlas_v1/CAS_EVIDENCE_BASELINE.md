# CAS Evidence Baseline V1

Research-only evidence note for the observation-first pattern atlas. No trading authorization.

## Regime boundary

The Closing Auction Session boundary is fixed at `2026-08-03`. Historical sessions before that date must remain `PRE_CAS`; sessions on or after that date must remain `POST_CAS` for closing-pattern research.

## Locally available post-CAS evidence

### 2026-08-03

Available session manifest reports:

- total messages: `156927`
- dropped messages: `0`
- parse failures: `0`
- reconnects: `3`
- coverage keys: `722`
- finalized at: `2026-08-03T15:35:00.767564`

Interpretation: usable for cash-auction forensic analysis through approximately 15:35, but not certified as a complete derivative tail through 15:40.

### 2026-08-04 — run `093005`

Available sealed evidence reports:

- total files: `98`
- total bytes: `104389430`
- total raw frames: `143646`
- total normalized rows: `1041828`
- raw valid: `true`
- normalized valid: `true`
- issues count: `0`
- sealed at UTC: `2026-08-04T10:35:51.238047Z`

The manifest contains normalized hourly partitions for NIFTY, BANKNIFTY, SENSEX and INDIA_VIX through UTC hour `10`. This is the strongest currently identified CAS forensic case and should be analysed separately as an expiry-session case study.

### 2026-08-05

A complete sealed post-15:15 manifest has not yet been established in this campaign. Do not classify the visible files as a complete CAS session until endpoint coverage and validation are proven.

## Initial forensic questions

1. What changed between the 15:00–15:15 continuous-market state and the auction-derived cash close?
2. Did index futures catch up to, reject, or overshoot the auction displacement between 15:30 and 15:40?
3. Was the NIFTY–SENSEX divergence broad-based or concentrated in a few constituents?
4. How did near-expiry CE and PE premium elasticity change around the auction result?
5. Did any displacement persist into the next session open?

## Evidence verdict

`CAS_FORENSIC_EVIDENCE_AVAILABLE_BUT_SAMPLE_INSUFFICIENT_FOR_EDGE`

The first post-CAS sessions may generate hypotheses and instrumentation requirements. They cannot establish statistical expectancy.
