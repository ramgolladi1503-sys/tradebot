# TREND_PULLBACK_v1 historical campaign methodology

The campaign exists to answer a falsifiable question: does the unchanged production strategy callable show a causal, after-cost structural edge on pinned NIFTY futures data?

## Causal boundary

At each trigger checkpoint the campaign supplies only completed bars through the trigger bar. The strategy signal is evaluated at trigger-bar end, and entry occurs at the next bar open. No signal-bar close fill is permitted.

## Feature ownership

VWAP, ATR, volume z-score, day range, ORB and structural anchors are computed from current-session history available at the checkpoint. Regime scoring uses `core.movement_regime.MovementRegimeClassifier`; candidate generation uses `generate_trend_pullback_candidates` directly.

## Exit model

The stop is placed beyond the strategy's support or resistance anchor with a frozen 0.10 ATR buffer. Target is frozen at 1.5 times initial risk. The maximum holding period is 15 bars. If stop and target are both touched in one bar, the stop is selected first.

## Evidence gates

A candidate requires sufficient trades, positive untouched-holdout expectancy, holdout profit factor, positive rolling OOS fraction, survival under 5 bps cost, and bounded session concentration. No parameters are optimized during the campaign.

## Claim ceiling

A pass produces `STRUCTURAL_EDGE_CANDIDATE`. It cannot produce an option-replay or live-trading verdict because the source contains futures OHLCV rather than executable historical option quotes and quantities.
