# Strategy Matrix

This audit classifies the active movement strategies as implemented, but not yet edge-proven.

| Strategy | File | Market Thesis | Verdict | Notes |
| --- | --- | --- | --- | --- |
| opening_drive | `strategies/movement/opening_drive.py` | Open-session impulse after a confirming move | IMPLEMENTED_BUT_HEURISTIC | Fixed entry logic, no durable edge proof |
| opening_range_retest | `strategies/movement/opening_range_breakout.py` | Opening range breakout and retest continuation | IMPLEMENTED_BUT_HEURISTIC | Strongly regime-dependent, still threshold driven |
| compression_breakout | `strategies/movement/compression_breakout.py` | Compression resolves into breakout | IMPLEMENTED_BUT_HEURISTIC | Needs replay by regime and cost |
| trend_pullback | `strategies/movement/trend_pullback.py` | Pullbacks inside trend resume the move | IMPLEMENTED_BUT_HEURISTIC | Most defensible structurally, still unproven |
| vwap_reclaim_rejection | `strategies/movement/vwap_reclaim.py` | VWAP reclaim/rejection drives continuation | IMPLEMENTED_BUT_HEURISTIC | Good thesis, still generic thresholds |
| failed_breakout_trap | `strategies/movement/failed_breakout_trap.py` | Failed breakouts reverse into traps | IMPLEMENTED_BUT_HEURISTIC | Sensitive to quote quality and regime |
| exhaustion_reversal | `strategies/movement/exhaustion_reversal.py` | Overextension fades back | IMPLEMENTED_BUT_HEURISTIC | Needs explicit expectancy proof |
| mean_reversion_extension | `strategies/movement/mean_reversion_extension.py` | Range extension mean reverts | IMPLEMENTED_BUT_HEURISTIC | Can be cost-killed in wide spreads |
| event_volatility_expansion | `strategies/movement/event_volatility_expansion.py` | Event-driven volatility expansion | IMPLEMENTED_BUT_HEURISTIC | Requires event truth and slippage proof |
| option_pressure | `strategies/movement/option_pressure.py` | Pressure / confirmation in option flow | IMPLEMENTED_BUT_HEURISTIC | Heuristic confirmation layer |
| late_day_momentum | `strategies/movement/late_day_momentum.py` | Late-day trend continuation | IMPLEMENTED_BUT_HEURISTIC | Time-dependent, still not validated |
| no_trade_chop | `strategies/movement/no_trade_chop.py` | Conservative no-trade in chop | FALLBACK_ARTIFACT | Safety artifact, not an edge engine |

## Common observations

1. The strategies are mostly built from regime scores, VWAP, range, momentum, trap, and confirmation logic.
2. They are not yet outcome-calibrated at the strategy level.
3. They do account for spread/liquidity in the implementation, which is good.
4. They do not yet prove that the surviving candidates beat costs over time.
5. The repo should treat them as candidate generators, not as proven alpha.
