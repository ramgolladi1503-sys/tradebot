# Cross-Strike Diffusion Discovery V1

## Objective

Test whether coherent repricing in neighbouring NIFTY option strikes leads a temporarily lagging contract, creating a short-horizon buy-side catch-up opportunity.

This mechanism is intentionally different from the late-day CE inventory-rebound candidate. It studies asynchronous price discovery across strikes rather than capitulation followed by reversal.

## Frozen design

- Eight theory-led mechanisms only.
- BUY-only CE and PE research.
- Completed one-minute candles only.
- Entry at the next same-contract one-minute open.
- Five-minute same-contract close exit.
- Chronological 75% research / 25% untouched holdout.
- Five expanding out-of-fold tests with thresholds recalculated from prior sessions only.
- Maximum two signals per session, separated by at least 15 minutes.
- OOF requires at least 80 trades across 60 sessions.
- Holdout requires at least 25 trades across 20 sessions.
- Positive bootstrap lower confidence bound required in both OOF and holdout.
- 1.0% total premium-return friction stress.
- Five-minute delayed-entry control must be materially weaker.

## Claim boundary

Historical OHLCV structural research only. No observed spread, bid/ask execution, paper eligibility, live eligibility or production integration is claimed.
