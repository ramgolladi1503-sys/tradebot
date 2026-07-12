# NIFTY Futures Authenticated Fetch

## Status
`VALID_AUTHENTICATED_SESSION_ACQUIRED`

## Phase 1 — Audit the existing acquisition path
- **Method**: `upstox_client.HistoryApi.get_historical_candle_data1()`
- **Supported intervals**: 1minute, 3minute, 5minute, etc.
- **Authentication**: Upstox access token
- **Volume**: Returned inline in the API response.
- **Verdict**: `USER_AUTHENTICATED_MINUTE_CANDLE_SOURCE_AVAILABLE`

## Phase 2 — Resolve an actual dated futures contract
- Exchange: NSE_FO
- Instrument Token: NSE_FO|61093
- Trading Symbol: NIFTY26JULFUT
- Underlying: NIFTY
- Instrument Type: FUTIDX
- Expiry: 2026-07-28
- Lot Size: 65
- Tick Size: 0.1
