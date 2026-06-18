# HTF_RANGE_EXPANSION Strategy Specification

This document defines the exact execution logic and governance constraints for the `HTF_RANGE_EXPANSION` candidate strategy.

> [!CAUTION]
> This strategy is mathematically locked. Do not modify its logic, optimize its thresholds, or alter its structural mechanics. 

## 1. Core Logic & Mechanics

### Entry Conditions
- **Trigger**: The closing price of the current 15m candle breaches the high or low of the structural Opening Drive.
- **Opening Drive Definition**: The highest high and lowest low recorded between 09:15 and 10:00 (the first 3 15-minute candles).

### Regime Gate
- **Strict Isolation**: The strategy evaluates signals *exclusively* under the `VOL_EXPANSION` market regime. It will automatically return `REJECT_VOLATILITY` in any other state (`CHOP`, `TREND_UP`, `TREND_DOWN`, `RANGE`).

### Structural Alignment
- **15m / 30m Trend**: The direction of the Opening Drive breakout must align perfectly with the prevailing trailing trend of the previous 15m and 30m periods. If the breakout is long, but the trailing 30m trend is down, it is rejected.

### Execution Timing
- **Causality & Leakage Prevention**: Execution is strictly forbidden on the same 1-minute candle that triggers the 15m close. Execution inherently occurs on the `next 1m open` to simulate true paper latency.
- **Session Gating**: No signals are accepted before 10:15 or after 14:30.

### Exclusion Rules
- **Gap Expansion Warning**: If the market opens with a gap `> 0.5%` compared to the prior day's close, the day is mathematically poisoned. The strategy rejects all signals under `REJECT_GAP_EXPANSION`.

### Stop & Target Logic
- **Stop Loss**: Set to the opposite side of the Opening Drive (e.g., the low of the drive if breaking out high). Minimum stop distance is clamped to 2.0 index points.
- **Target**: Static `1R` or `2R` geometry derived directly from the physical width of the Opening Drive stop. 
- **Time Stop**: EOD auto-square-off enforced at 15:15.

### Option Selection Logic
- N/A for raw evaluation. Execution utilizes the `INDEX_OPTION_BUY` proxy framework modeled via ATM/ITM derivatives natively wrapped in the execution daemon.

## 2. Operational Status
- **Status**: `REAL_PAPER_VALIDATION`
- **Execution Mode**: Observation only. No live broker routing permitted.

## 3. Known Failure Modes
- **Extreme Slippage**: Stress tests indicate the mathematical edge deteriorates significantly if slippage expands beyond 2x baseline assumptions.
- **Cost Drag**: ATM options exhibit minor structural drag compared to native Futures.

## 4. Forbidden Modifications
1. Do not remove the `VOL_EXPANSION` gate.
2. Do not allow same-candle execution.
3. Do not alter the timezone or session gating limits.
4. Do not weaken the Gap Expansion exclusion.
5. Do not introduce live broker order routing.
6. Do not tune or optimize stop/target thresholds.
