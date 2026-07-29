# Late-Day CE Inventory Rebound V9 — Invalidated by Causality Audit

Principal verdict: `INVALID_FUTURE_ENTRY_PRICE_SIGNAL_MEMBERSHIP_LEAK`

The prior V9 publication is invalid as a causal trading signal contract.

The signal-membership oracle used `entry_price_next_open`—the first same-contract option open one minute after the completed signal—to:

- decide whether entry premium was between ₹30 and ₹150; and
- rank simultaneous candidates by distance from ₹150.

That value is unavailable at the signal timestamp. A future fill may be used for economic reconstruction only after signal membership has already been frozen; it cannot determine whether a signal exists or which candidate is selected.

The previous OOF, holdout, controls, concentration and friction results therefore do not certify a causal edge, even though their arithmetic may reproduce exactly.

Required continuation:

1. replace entry-price eligibility with a signal-time-observable field, such as completed-bar close;
2. replace the future-entry tie-break with a causal tie-break;
3. freeze the repaired rule before evaluating outcomes;
4. rebuild all OOF, controls, chronological holdout, concentration and friction evidence from scratch.

No paper or live authorization is granted.
