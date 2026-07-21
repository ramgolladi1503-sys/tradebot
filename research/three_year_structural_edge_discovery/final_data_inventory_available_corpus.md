# Final Data Inventory For Available Corpus

Canonical epoch source: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay` classified as `TRUSTED_UNDERLYING_1M_CANDLES` for complete multi-index sessions.

Complete epoch: `20240701` through `20260710`, `500` sessions.

Excluded: older `data/backtest/one_minute` CSVs because provenance/synthetic/mock/fallback fields are absent and coverage is mostly NIFTY-only; recent `.runtime/market_data` tick captures because they are July 2026 fragments and not a continuous compatible epoch extension.

Safety: read_only=true; is_order_action=false; broker_api_called=false; execution_eligibility=false; allowed_for_live_execution=false.
