# Strategy Contract and Edge Readiness Audit

## Overview
This audit confirms that the 11 active movement strategies have been refactored to consume strategy parameters from a WFA-ready profile layer (`StrategyParameterProfile`) without violating the core safety contracts.

## 1. What Values Were Refactored to Profiles
Across all 11 strategies, hardcoded constants determining thresholds (e.g., minimum scores, maximum distances, maximum timing parameters) have been relocated to the `DEFAULT_PROFILES` map in `core/strategy_parameter_profiles.py`.

The strategies refactored include:
- `opening_drive.py`
- `opening_range_breakout.py`
- `compression_breakout.py`
- `trend_pullback.py`
- `vwap_reclaim.py`
- `failed_breakout_trap.py`
- `exhaustion_reversal.py`
- `mean_reversion_extension.py`
- `event_volatility_expansion.py`
- `late_day_momentum.py`
- `option_pressure.py`

In each strategy, local variables are dynamically injected at evaluation time using `get_default_profile(...)`. If the profile overrides values, they are gracefully accepted. Otherwise, they fall back to precisely the original hardcoded values.

## 2. Evidence That No Fallback Behavior Was Weakened
- The strategy generators still do not bypass or catch quote-quality exceptions (e.g. stale/fallback quotes).
- The `score_candidate` logic in `core/opportunity_scoring.py` retains the original hard downgrade behaviors.
- Explicit tests were written (`tests/test_fallback_never_executable.py`) proving that even if `promotion_state = "PROMOTED"`, any candidate carrying a downgrade for `fallback_quote_data` or other truth gate failure will remain in `ADVISORY_CANDIDATE` or `NO_TRADE_CANDIDATE`.
- Strategy fallback checks (such as verifying `spot`, `vwap`, etc. are not None and returning empty candidate lists if miss-ing) remain completely unmodified.

## 3. Confirmation That Candidates Remain Read-Only
- All strategy files generate `StrategyCandidate` objects cleanly without side-effects.
- They do not submit orders, modify execution flags, ping brokers, or interact with active subscriptions.
- The WFA-ready `make_candidate` helper safely writes deterministic `params_used` and `params_hash` metadata into `lineage`, purely for passive telemetry and offline analysis.
- The `promotion_state` logic in `core/opportunity_scoring.py` enforces constraints conservatively (downgrading when unknown, experimental, or advisory-only), but does not itself initiate any active trade actions.

## Conclusion
The refactor succeeds in making the active strategies parameter-profile-driven while completely preserving live-trade isolation and safety gate dominance.

## Parameter Refactor Tracking Tables

### Opening Drive
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| opening_drive_v1 | MAX_OPENING_DRIVE_MINUTES | 20 | MAX_OPENING_DRIVE_MINUTES | 20 | Exact Match | int |
| opening_drive_v1 | MIN_OPEN_MOVE_PCT | 0.0015 | MIN_OPEN_MOVE_PCT | 0.0015 | Exact Match | float |
| opening_drive_v1 | MIN_VWAP_ALIGNMENT_PCT | 0.0005 | MIN_VWAP_ALIGNMENT_PCT | 0.0005 | Exact Match | float |

### Opening Range Breakout
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| opening_range_breakout_v1 | MIN_RETEST_MINUTES | 15 | MIN_RETEST_MINUTES | 15 | Exact Match | int |
| opening_range_breakout_v1 | MAX_RETEST_MINUTES | 90 | MAX_RETEST_MINUTES | 90 | Exact Match | int |
| opening_range_breakout_v1 | MAX_RETEST_DISTANCE_PCT | 0.0018 | MAX_RETEST_DISTANCE_PCT | 0.0018 | Exact Match | float |
| opening_range_breakout_v1 | MIN_BREAKOUT_DISTANCE_PCT | 0.0008 | MIN_BREAKOUT_DISTANCE_PCT | 0.0008 | Exact Match | float |

### Compression Breakout
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| compression_breakout_v1 | MAX_RANGE_WIDTH_PCT | 0.35 | MAX_RANGE_WIDTH_PCT | 0.35 | Exact Match | float |
| compression_breakout_v1 | MAX_ATR_RATIO | 0.75 | MAX_ATR_RATIO | 0.75 | Exact Match | float |
| compression_breakout_v1 | MIN_COMPRESSION_SCORE | 0.5 | MIN_COMPRESSION_SCORE | 0.5 | Exact Match | float |
| compression_breakout_v1 | MIN_BREAKOUT_DISTANCE_PCT | 0.0008 | MIN_BREAKOUT_DISTANCE_PCT | 0.0008 | Exact Match | float |
| compression_breakout_v1 | MIN_VWAP_ALIGNMENT_PCT | 0.0004 | MIN_VWAP_ALIGNMENT_PCT | 0.0004 | Exact Match | float |

### Trend Pullback
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| trend_pullback_v1 | MIN_TREND_SCORE | 0.45 | MIN_TREND_SCORE | 0.45 | Exact Match | float |
| trend_pullback_v1 | MAX_PULLBACK_DISTANCE_PCT | 0.0035 | MAX_PULLBACK_DISTANCE_PCT | 0.0035 | Exact Match | float |
| trend_pullback_v1 | MIN_STRUCTURE_RESUME_PCT | 0.0004 | MIN_STRUCTURE_RESUME_PCT | 0.0004 | Exact Match | float |

### VWAP Reclaim
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| vwap_reclaim_v1 | MIN_VWAP_DISTANCE_PCT | 0.00035 | MIN_VWAP_DISTANCE_PCT | 0.00035 | Exact Match | float |
| vwap_reclaim_v1 | MAX_VWAP_ENTRY_DISTANCE_PCT | 0.0035 | MAX_VWAP_ENTRY_DISTANCE_PCT | 0.0035 | Exact Match | float |
| vwap_reclaim_v1 | MAX_CHOP_SCORE | 0.55 | MAX_CHOP_SCORE | 0.55 | Exact Match | float |

### Failed Breakout Trap
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| failed_breakout_trap_v1 | MAX_REENTRY_DISTANCE_PCT | 0.0035 | MAX_REENTRY_DISTANCE_PCT | 0.0035 | Exact Match | float |
| failed_breakout_trap_v1 | MIN_FAILED_BREAK_DISTANCE_PCT | 0.0006 | MIN_FAILED_BREAK_DISTANCE_PCT | 0.0006 | Exact Match | float |
| failed_breakout_trap_v1 | MIN_TRAP_EVIDENCE_SCORE | 0.45 | MIN_TRAP_EVIDENCE_SCORE | 0.45 | Exact Match | float |

### Exhaustion Reversal
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| exhaustion_reversal_v1 | MIN_STRETCH_FROM_VWAP_PCT | 0.005 | MIN_STRETCH_FROM_VWAP_PCT | 0.005 | Exact Match | float |
| exhaustion_reversal_v1 | MAX_ENTRY_STRETCH_PCT | 0.018 | MAX_ENTRY_STRETCH_PCT | 0.018 | Exact Match | float |
| exhaustion_reversal_v1 | MIN_EXHAUSTION_SCORE | 0.5 | MIN_EXHAUSTION_SCORE | 0.5 | Exact Match | float |
| exhaustion_reversal_v1 | MAX_CONTINUATION_PRESSURE_SCORE | 0.55 | MAX_CONTINUATION_PRESSURE_SCORE | 0.55 | Exact Match | float |

### Mean Reversion Extension
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| mean_reversion_extension_v1 | MIN_RANGE_OR_CHOP_SCORE | 0.45 | MIN_RANGE_OR_CHOP_SCORE | 0.45 | Exact Match | float |
| mean_reversion_extension_v1 | MIN_EXTENSION_FROM_VWAP_PCT | 0.0035 | MIN_EXTENSION_FROM_VWAP_PCT | 0.0035 | Exact Match | float |
| mean_reversion_extension_v1 | MAX_EXTENSION_FROM_VWAP_PCT | 0.014 | MAX_EXTENSION_FROM_VWAP_PCT | 0.014 | Exact Match | float |
| mean_reversion_extension_v1 | MAX_TREND_CONTINUATION_SCORE | 0.55 | MAX_TREND_CONTINUATION_SCORE | 0.55 | Exact Match | float |

### Event Volatility Expansion
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| event_volatility_expansion_v1 | MIN_VOL_EXPANSION_SCORE | 0.4 | MIN_VOL_EXPANSION_SCORE | 0.4 | Exact Match | float |
| event_volatility_expansion_v1 | MIN_IMPULSE_FROM_VWAP_PCT | 0.0025 | MIN_IMPULSE_FROM_VWAP_PCT | 0.0025 | Exact Match | float |
| event_volatility_expansion_v1 | MAX_CHASE_DISTANCE_PCT | 0.014 | MAX_CHASE_DISTANCE_PCT | 0.014 | Exact Match | float |
| event_volatility_expansion_v1 | MIN_VOLUME_Z | 1.2 | MIN_VOLUME_Z | 1.2 | Exact Match | float |
| event_volatility_expansion_v1 | MIN_ATR_EXPANSION_RATIO | 1.15 | MIN_ATR_EXPANSION_RATIO | 1.15 | Exact Match | float |

### Late Day Momentum
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| late_day_momentum_v1 | MIN_MINUTES_SINCE_OPEN | 240 | MIN_MINUTES_SINCE_OPEN | 240 | Exact Match | int |
| late_day_momentum_v1 | MIN_MINUTES_TO_CLOSE | 20 | MIN_MINUTES_TO_CLOSE | 20 | Exact Match | int |
| late_day_momentum_v1 | MIN_DIRECTIONAL_SCORE | 0.45 | MIN_DIRECTIONAL_SCORE | 0.45 | Exact Match | float |
| late_day_momentum_v1 | MIN_VWAP_DISTANCE_PCT | 0.002 | MIN_VWAP_DISTANCE_PCT | 0.002 | Exact Match | float |
| late_day_momentum_v1 | MAX_CHASE_DISTANCE_PCT | 0.012 | MAX_CHASE_DISTANCE_PCT | 0.012 | Exact Match | float |
| late_day_momentum_v1 | MAX_CHOP_SCORE | 0.5 | MAX_CHOP_SCORE | 0.5 | Exact Match | float |

### Option Pressure
| Strategy ID | Old Constant | Old Value | New Key | New Value | Equality Proof | Type |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| option_pressure_v1 | MIN_PRESSURE_SCORE | 0.45 | MIN_PRESSURE_SCORE | 0.45 | Exact Match | float |

## Strategy Parameter Transmission Matrix

| Strategy | Generator Function | make_candidate Before | make_candidate After | params_used Count | params_hash Count | promotion_state Count |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| opening_drive | generate_opening_drive_candidates | 1 | 1 | 1 | 1 | 1 |
| opening_range_breakout | generate_opening_range_retest_candidates | 1 | 1 | 1 | 1 | 1 |
| compression_breakout | generate_compression_breakout_candidates | 1 | 1 | 1 | 1 | 1 |
| trend_pullback | generate_trend_pullback_candidates | 1 | 1 | 1 | 1 | 1 |
| vwap_reclaim | generate_vwap_reclaim_rejection_candidates | 1 | 1 | 1 | 1 | 1 |
| failed_breakout_trap | generate_failed_breakout_trap_candidates | 1 | 1 | 1 | 1 | 1 |
| exhaustion_reversal | generate_exhaustion_reversal_candidates | 1 | 1 | 1 | 1 | 1 |
| mean_reversion_extension | generate_mean_reversion_extension_candidates | 1 | 1 | 1 | 1 | 1 |
| event_volatility_expansion | generate_event_volatility_expansion_candidates | 1 | 1 | 1 | 1 | 1 |
| late_day_momentum | generate_late_day_momentum_candidates | 1 | 1 | 1 | 1 | 1 |
| option_pressure | generate_option_pressure_candidates | 0 | 0 | 1 (Direct Constructor) | 1 (Direct Constructor) | 1 (Direct Constructor) |
