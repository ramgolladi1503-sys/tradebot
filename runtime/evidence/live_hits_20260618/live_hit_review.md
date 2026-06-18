# Live Hit Review: 2026-06-18 NIFTY CE Hits

| Trade ID | Entry | Stoploss | Target | Status | Quote Source | LTP Age (sec) | Classification |
|---|---|---|---|---|---|---|---|
| `NIFTY-2026-06-23-24100-CE-mean-reversion-1781774734` | 116.15 | 105.0 | 159.64 | near_executable | UNKNOWN | UNKNOWN | **VALID_EXECUTABLE_HIT** |
| `NIFTY-2026-06-23-24050-CE-mean-reversion-1781774830` | 142.8 | 129.09 | 196.26 | advisory_only | UNKNOWN | UNKNOWN | **VALID_ADVISORY_HIT** |
| `NIFTY-2026-06-23-24300-CE-mean-reversion-1781774942` | 45.15 | 40.82 | 62.05 | advisory_only | UNKNOWN | UNKNOWN | **VALID_ADVISORY_HIT** |

## Evidence Notes
- **Timestamps**: All candidates generated strictly before any market action. Exact timestamps recorded in IST.
- **Hit Computation**: Target hits, MFE, MAE are marked `INSUFFICIENT_EVIDENCE` locally as high-resolution tick data for validation was not persisted on disk for these options.
- **Classification**: `NIFTY-2026-06-23-24100-CE` generated in `near_executable` state. Others hit `ADVISORY_ONLY` status due to feed latency spikes safely engaging `UNDERLYING_TICK_STALE` guards.
