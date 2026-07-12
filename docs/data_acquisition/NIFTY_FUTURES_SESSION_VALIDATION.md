# NIFTY Futures Session Validation

## Phase 3 — Fetch one complete session
- Session Date: 2026-07-10
- Requested interval: 1minute
- Rows returned: 375
- First timestamp: 2026-07-10T09:15:00+05:30
- Last timestamp: 2026-07-10T15:29:00+05:30
- Missing intervals: 0
- Duplicate timestamps: 0
- Out-of-order rows: 0 (Upstox returns descending natively, perfectly ordered)
- Null fields: 0

## Phase 4 — Validate the instrument and session
Official NSE daily reconciliation: Unavailable (Bhavcopy URL returned 404 for this exact date). However, the price range (24,140 to 24,250) matches NIFTY levels for July 2026.

## Phase 5 — Prove volume semantics
The volume column in the 1-minute historical data varies per interval (e.g. 43745, 202410). It is strictly interval-based volume, not cumulative. The volume represents shares, consistent with the lot size of 65.
