# Phase 7: Replay Calibration Wiring Report

## Enhancements Implemented
The `IntelligenceReplayEngine` (`core/intelligence/replay/intelligence_replay.py`) was structurally wired to mimic interaction with the TradeBot core analytical stores (`tick_store`).

1. **Realistic Data Fetching**: Added the `_fetch_tick_data` abstraction simulating calls to `get_forward_realized_volatility` and `get_option_spreads`.
2. **Honest Insufficient Evidence**: Instead of blindly returning `True`, the calibrator evaluates the *valid* samples. Even if 50 events occurred, if only 10 have valid intersecting tick data, the engine actively bails out and returns `INSUFFICIENT_EVIDENCE`.
3. **Strict Output Shape**: The return dictionary guarantees keys for `forward_vol_multiplier_mean`, `spread_widening_bps`, and `confidence_interval`.
4. **No Fake Calibration**: No fake positive edge is assigned. The engine defaults entirely to returning `INSUFFICIENT_EVIDENCE` until the underlying TradeBot `tick_store.py` is definitively wired to return proper vectors in production.
