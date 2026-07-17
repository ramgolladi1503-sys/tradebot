# Strategy Contract Specification

## Version Info
* **Strategy ID**: `REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1`
* **Version**: `1.0.0`
* **Contract Hash**: `65a42e96705fd875814bb54547a8dc4675407ff2ba204bf3c75f91147f353eb4`

## Timing Rules
* **Opening Window**: `09:15 - 09:44` (based on bar-open timestamps).
* **Opening Window Complete**: `09:45`
* **Decision Cutoff Time**: `14:45` (completed bar at 14:45).
* **Earliest Entry Time**: `14:46`
* **Mandatory Final Exit Time**: `15:15`
* **Maximum Holding Period**: 30 minutes.

## Core Features
1. **NIFTY Opening Return**: `opening_close / session_open - 1`
2. **Opening Close Location**: `(opening_close - opening_low) / (opening_high - opening_low)` (Long >= 0.75, Short <= 0.25).
3. **Retained Move Fraction**: `(decision_close - session_open) / (opening_close - session_open)` (>= 0.50).
4. **Session price anchor**: `SESSION_TYPICAL_PRICE_MEAN` (average of `(high + low + close)/3` up to `14:45`).
5. **BANKNIFTY Confirmation**: Boolean condition (Long > 0, Short < 0).

## Rejection Codes
Enforced in order:
* `MISSING_NIFTY`
* `MISSING_BANKNIFTY`
* `INTERVAL_MISMATCH`
* `OPENING_WINDOW_INCOMPLETE`
* `DECISION_WINDOW_INCOMPLETE`
* `TIMESTAMP_MISALIGNMENT`
* `TIMEZONE_UNRESOLVED`
* `DUPLICATE_TIMESTAMP`
* `OHLC_INVALID`
* `MANIFEST_MISMATCH`
* `DUPLICATE_CONTENT_ALIAS`
* `INSUFFICIENT_PRIOR_HISTORY`
