# Late-Day CE Inventory Rebound V10 — Causality Audit

Principal verdict: `INVALID_FUTURE_ENTRY_PRICE_SIGNAL_MEMBERSHIP_LEAK`

The published V9 signal-membership oracle is not causal.

It uses `entry_price_next_open`, the first same-contract option open one minute after the completed signal, to:

- decide whether a candidate's entry premium lies between ₹30 and ₹150; and
- rank simultaneous candidates by distance from ₹150.

This field is unavailable at the signal timestamp. A next-bar open may be used only after signal membership is frozen, for fill and P&L reconstruction. It cannot decide whether a signal exists or which contract is selected.

Therefore:

- the exact 52-of-52 oracle match only proves reproduction of the same leaked membership rule;
- the OOF, holdout, mirror, delayed-entry, concentration and friction results do not certify a causal edge;
- the V9 publication and frozen contract are invalidated;
- paper and live authorization remain false.

Required continuation:

1. replace the entry-premium filter with a signal-time-observable field such as completed-bar close;
2. replace the future-entry tie-break with a causal tie-break;
3. freeze the repaired rules before inspecting outcomes;
4. rebuild OOF, controls, chronological holdout, concentration and friction evidence from scratch.
