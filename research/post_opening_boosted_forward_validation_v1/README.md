# Post-Opening Boosted Forward Validation V1

The parent multi-horizon WFA produced 276 OOF signals but failed later-fold stability. Diagnostic inspection showed opening-period contamination. Because the 10:00 IST gate was selected after that OOF inspection, it is explicitly treated as development-derived rather than independent WFA evidence.

This campaign freezes the post-opening candidate and uses the previously unopened 98 chronological sessions as two sequential blocks:

- first half: validation;
- second half: final certification, opened only if validation passes.

The model, causal features, exact entry, candidate horizons, confidence quantiles, 1% friction objective, threshold, signal cap and 10:00 gate are trained or frozen using research sessions only. Nothing is retrained after validation. Certification includes opposite-wing, delayed-entry and non-model baseline controls.

Historical option OHLCV candle proxy only. No broker, paper, live or production authorization.
