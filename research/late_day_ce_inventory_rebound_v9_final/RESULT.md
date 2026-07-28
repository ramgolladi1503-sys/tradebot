# Late-Day CE Inventory Rebound V9 — Final Research Classification

Principal verdict: `STRUCTURAL_EDGE_FOUND_LATE_DAY_CE_INVENTORY_REBOUND_5M_WITH_1PCT_FRICTION_SURVIVAL_LIMIT`

## Mechanism

The candidate buys a NIFTY call only after a late-day, high-volume call-premium capitulation occurs while the same-strike put expands strongly. The hypothesis is that extreme short-horizon CE/PE asymmetry creates a temporary option-inventory overshoot followed by a five-minute CE rebound.

This is not a conventional underlying-price breakout or indicator crossover. The signal is defined from the interaction of:

- CE return shock;
- acceleration of that shock;
- abnormal CE volume;
- same-strike PE expansion;
- CE-versus-PE response asymmetry;
- same-expiry option-surface participation;
- expiry distance, premium and time-of-day constraints.

## Frozen trade contract

- Instrument: NIFTY CE only.
- Signal window: 13:00–14:50 IST.
- DTE: 0–7.
- Entry premium: ₹30–₹150.
- Maximum one trade per session.
- Entry: same-contract option open exactly one minute after the completed signal.
- Exit: same-contract option close exactly five minutes after the signal.
- No stop/target overlay was optimized.
- Reject when observed or conservatively estimated round-trip friction exceeds 1.0% of option premium.

The machine-readable contract is `runtime/research/late_day_ce_inventory_rebound_v9_final/frozen_strategy_contract.json`.

## Independent signal reconstruction

- Research sessions: 292.
- Holdout sessions: 98.
- Independent oracle signals: 52.
- Published primary signals: 52.
- Missing: 0.
- Extra: 0.
- Verdict: `PASS_INDEPENDENT_SIGNAL_MEMBERSHIP_ORACLE`.

The oracle rebuilt the features, chronological folds, prior-only quantile thresholds and session-level selection without importing the discovery implementation. It requested identity columns only and did not use outcome or P&L values.

## Exact economic reconstruction

Entry and exit economics were independently rebuilt directly from the preserved option OHLCV:

- next-minute entry maximum error: 0.0;
- five-minute close-change maximum error: approximately 3.6e-15;
- published net-return maximum error: approximately 7.1e-15.

The earlier V3 publication was invalidated because it described a 20-minute exit while consuming five-minute labels. Only the corrected five-minute contract is authoritative.

## Results at 0.1% total friction

### Out-of-fold research

- Trades: 40.
- Profit factor: 2.5861.
- Mean return: +2.7468%.
- Median return: +2.9094%.
- Win rate: 65.0%.
- Four of four folds positive.
- Remove top two winners PF: 2.0949.
- Bootstrap mean 95% lower bound: +0.1970%.

### Untouched chronological holdout

- Trades: 12.
- Profit factor: 3.2165.
- Mean return: +4.2993%.
- Median return: +3.3612%.
- Win rate: 66.7%.
- Remove top two winners PF: 1.4257.
- Bootstrap mean 95% lower bound: -1.1894%.

### Controls

- Same-strike PE mirror control: PF 0.4070, mean -5.6048%.
- Five-minute delayed CE control: PF 2.4649, mean +3.8613%.

## Friction boundary

The combined OOF, holdout, top-two-winner-removal, fold, mirror and delayed-entry gate passes at total premium-return friction of:

- 0.1%;
- 0.5%;
- 1.0%.

It fails at 1.5% and above. At 1.0%:

- OOF PF: 1.8919;
- OOF mean: +1.8468%;
- OOF median: +2.0094%;
- OOF remove-top-two PF: 1.5028;
- positive OOF folds: 3/4;
- holdout PF: 2.5178;
- holdout mean: +3.3993%;
- holdout median: +2.4612%;
- holdout remove-top-two PF: 1.0338.

At 1.5%, the holdout remains profitable in aggregate but fails the concentration gate after removing its two largest winners. The failure is preserved; no threshold or trade rule was changed to rescue it.

## Claim boundary

This is a historical option-OHLCV **structural research edge** with a declared 1.0% friction-survival limit.

It is not:

- bid/ask execution certified;
- proof of future profitability;
- paper authorized;
- live authorized;
- production integrated.

The holdout contains only 12 trades, and its bootstrap confidence interval crosses zero. Forward quote capture must prove that actual round-trip friction stays below 1.0% before paper eligibility can be considered.
