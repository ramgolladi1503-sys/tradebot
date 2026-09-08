# PR #718 Mixed-Source Logic Integrity Repair V2

## Result

The frozen 769 canonical raw-candidate intents were replayed against the existing Upstox expired-option archive after repairing exact-ATM, expiry, entry-lag and fill semantics. No strategy formula or threshold was changed.

## Authority boundary

These results are a `PRICE_STRUCTURE_CANDIDATE_OVERLAY` using `COMMON_OPTION_OVERLAY_V1`. They are not native strategy PF and not executable-strategy evidence because historical Phase-2 liquidity, freshness and option-confirmation truth is unavailable.

## Reconciliation

- Intents: 769
- Exact-ATM trades: 216
- Blockers: 553
- WFA survivors: 0
- Holdout outcomes read: false

## Corrected blockers

- Exact ATM unavailable: 356
- Expiry-universe coverage missing: 94
- Same-session option authority missing: 101
- Entry or exit timing unavailable: 2

## Gates

- Exact NIFTY ATM: 50-point ROUND_HALF_UP
- True nearest non-expired expiry resolved from metadata before candle coverage
- No later-expiry or distant-strike substitution
- Entry strictly after signal and within 120 seconds
- Gap-through stop uses the worse of stop or bar open for a long option
- Three normalizations reported: one-lot rupee, per-unit, return-percent
- ATM ±50 is sensitivity-only and excluded from verdicts
- Local reconstructed-source focused suite: 26 passed
- GitHub complete-repository publication suite: 32 passed in 0.54 seconds
- Two independent directory runs produced byte-identical outputs
- Independent oracle passed

## Final verdict

`INSUFFICIENT_OPTION_TRANSLATION_SAMPLE`

No strategy survives the frozen development/validation gate. Holdout remains sealed.
