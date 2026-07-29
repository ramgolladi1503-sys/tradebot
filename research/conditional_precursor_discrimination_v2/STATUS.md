# Conditional Precursor Discrimination V2 — Current Status

Principal verdict: `INVALID_FUTURE_ENTRY_PRICE_SIGNAL_MEMBERSHIP_LEAK`

The late-day CE rebound candidate is not currently a valid causal structural edge.

The V5 signal-membership oracle used `entry_price_next_open`, a value observed one minute after the completed signal, both as an eligibility filter and as a candidate tie-break. Exact reconstruction therefore reproduced the same future-information dependency rather than proving signal-time causality.

The V9 result, final decision and frozen contract are invalidated. No paper or live authorization exists.

Next valid step: rerun the candidate with signal membership frozen using only completed-bar observables, then rebuild OOF, controls, chronological holdout, concentration and friction evidence from scratch.
