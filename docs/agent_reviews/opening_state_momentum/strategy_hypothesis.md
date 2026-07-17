# Strategy Hypothesis

## Identifier
`REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1`

## Version
`1.0.0`

## Economic Mechanism
The core economic premise of this strategy is that an opening information shock (measured between 09:15 and 09:45 IST) that remains directionally coherent through the session predicts a profitable continuation during the final part of the trading session (after 14:45 IST).

The strategy assumes that:
1. An unusual directional price movement on NIFTY in the first 30 minutes indicates a strong opening shock.
2. Confirmation by BANKNIFTY ensures that the move is index-wide rather than driven by a single stock.
3. Midpoint and session anchor (Typical Price Mean) persistence at 14:45 IST ensures that the trend remains intact and has not fully mean-reverted.
4. Retained move fraction of at least 50% guarantees that the index did not retrace more than half of the initial opening shock.
