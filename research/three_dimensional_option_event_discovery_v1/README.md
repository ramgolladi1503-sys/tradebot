# Three-Dimensional Option Event Discovery V1

## Objective

Discover whether NIFTY buy-option edge appears only when a contract participates in a causal three-dimensional event:

1. **time transition** — current completed five-minute bar versus the same contract's previous completed bar;
2. **local strike neighbourhood** — the contract versus nearby strikes in the same expiry and wing;
3. **CE/PE mirror** — the same strike on the opposite wing at the same timestamp.

This is intentionally different from the failed synchronised surface-discount rebound family. It does not treat the whole wing as one state. It asks whether edge appears when a local strike tube behaves differently from both its nearby strikes and its mirror contract.

## Frozen boundaries

- NIFTY historical option OHLCV event universe only.
- BUY CE/PE only.
- Premium range: 30 to 300.
- DTE: 0 to 7.
- Exact entry: same-contract next one-minute open after completed signal.
- Exact outcome: same-contract five-minute close change.
- No stop, target, broker, paper, or live execution.
- 1% total premium-return friction stress must survive.
- Latest 25% chronological holdout remains unopened unless an OOF survivor exists.

## OOF gates

A mechanism must pass all of the following before holdout is opened:

- at least 90 OOF trades;
- at least 65 OOF sessions;
- PF >= 1.30;
- positive mean and non-negative median;
- PF >= 1.10 after removing the five largest winners;
- stress PF >= 1.05 after 1% friction;
- bootstrap lower bound above zero;
- at least 3 of 4 chronological folds positive;
- no largest-winner or largest-session dominance above 18%;
- mirror and delayed-entry controls must not explain the result.

## Claim boundary

Even if a survivor appears, the claim remains historical five-minute candle-proxy research only. Execution certification is blocked until timestamp-aligned bid/ask/spread evidence exists.
