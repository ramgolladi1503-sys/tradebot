# Strategy Coverage & Time-of-Day Analysis

- **Canonical Active Strategy**: `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1`
- **Supported Underlyings**: NIFTY (plus canonical derivatives / equities under shadow test)
- **Time-of-Day Coverage**:
  - `09:15 - 10:00 IST`: Morning opening range reversal discovery. Completed-bar evaluation on 1m/5m candles.
  - `10:00 - 14:30 IST`: Core session trend and mean-reversion evaluation.
  - `14:30 - 15:15 IST`: Final hour session wrap-up and closing momentum.
  - `15:15 - 15:30 IST`: End-of-day square-off and settlement; live quotes enforced.
