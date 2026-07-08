# Candidate Replay Data Source Decision Report

| Source | Setup | Candle | Stress | Certifiable | Blockers |
|--------|-------|--------|--------|-------------|----------|
| UPSTOX_UNDERLYING_OHLC | ✅ | ❌ | ❌ | ❌ | DATA_BLOCKED_UNDERLYING_ONLY_NO_OPTION_TRUTH |
| UPSTOX_OPTION_OHLC | ✅ | ✅ | ❌ | ❌ | DATA_BLOCKED_OPTION_OHLC_NO_SPREAD_TRUTH |
| LIVE_CAPTURED_OPTION_QUOTES | ✅ | ✅ | ✅ | ✅ |  |
| LIVE_CAPTURED_OPTION_DEPTH | ✅ | ✅ | ✅ | ✅ |  |
| BROKER_HISTORICAL_OPTION_TICKS | ✅ | ✅ | ✅ | ✅ |  |
| FIXTURE_DATA | ❌ | ❌ | ❌ | ❌ | DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY |
| MOCK_DATA | ❌ | ❌ | ❌ | ❌ | DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY |
| SYNTHETIC_DATA | ❌ | ❌ | ❌ | ❌ | DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY |
| PROXY_DATA | ❌ | ❌ | ❌ | ❌ | DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY |

## Notes
- **UPSTOX_UNDERLYING_OHLC**: Upstox underlying OHLC can support setup reconstruction only.
- **UPSTOX_OPTION_OHLC**: Upstox option OHLC can support candle replay only if the harness has an explicit candle replay mode. Upstox OHLC cannot support stress replay without bid/ask spread or depth truth.
- **LIVE_CAPTURED_OPTION_QUOTES**: Live captured option quotes may support option LTP and spread-aware checks if quote contains bid/ask.
- **LIVE_CAPTURED_OPTION_DEPTH**: Live captured depth may support stress replay if coverage/provenance is complete.
- **BROKER_HISTORICAL_OPTION_TICKS**: Historical ticks with spread data can support stress replay.
- **FIXTURE_DATA**: FIXTURE_DATA must be non-certifiable.
- **MOCK_DATA**: MOCK_DATA must be non-certifiable.
- **SYNTHETIC_DATA**: SYNTHETIC_DATA must be non-certifiable.
- **PROXY_DATA**: PROXY_DATA must be non-certifiable.
