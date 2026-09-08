## Summary

Repairs PR #718's mixed-source option replay logic and reruns all 769 frozen canonical strategy intents using the existing Kite-underlying / Upstox-expired-option evidence only. No production strategy formula, threshold, broker, order, feed, risk, dashboard or live configuration was changed.

## Evidence authority

- Signal source: 769 frozen canonical intents previously emitted by production strategy owners from authoritative Kite NIFTY five-minute bars.
- Option source: authoritative raw Upstox expired-option one-minute responses.
- Evidence lane: `PRICE_STRUCTURE_CANDIDATE_OVERLAY`.
- Exit overlay: `COMMON_OPTION_OVERLAY_V1`.
- This is not native strategy PF and not executable-strategy evidence because historical Phase-2 liquidity, freshness and option-confirmation truth is unavailable.

## Logic repairs

- Resolves true nearest non-expired expiry from supplied metadata before checking candle coverage.
- Requires exact NIFTY 50-point ATM using `ROUND_HALF_UP`.
- Rejects distant-strike and later-expiry substitution.
- Requires entry strictly after signal and within 120 seconds.
- Uses adverse gap-through stop fills.
- Reports one-lot, per-option-unit and return-percent normalizations.
- Keeps ATM ±50 results sensitivity-only.
- Preserves typed completed-bar timestamps.
- Uses the parquet-declared UTC source timezone and converts to Asia/Kolkata.
- Corrects the regular five-minute session to 75 bar starts, 09:15 through 15:25.
- Excludes the unsupported November 1, 2024 Muhurat session from normal-session execution.

## Corrected rerun

- Canonical intents replayed: 769
- Exact-ATM trades: 216
- Blockers: 553
- Reconciliation: `216 + 553 = 769`
- Exact ATM unavailable: 356
- Expiry-universe coverage missing: 94
- Same-session option authority missing: 101
- Entry/exit timing unavailable: 2
- WFA survivors: 0
- Holdout outcomes read: false

## Strategy result

No strategy survives the frozen development/validation gate across the required sample and normalization checks. Opening Drive remains positive in development but fails sharply in validation. Other apparent positives have inadequate validation samples or fail at least one normalization.

## Verification

- Independent oracle: `PASS_INDEPENDENT_ORACLE`
- Determinism: `PASS_DETERMINISM_GATE`
- Timestamp authority: all 1,479 underlying parquet files declare UTC timestamp metadata.
- Focused local suite: `26 passed`
- Full branch suite is executed by the publication workflow before commit.

## Final verdict

`INSUFFICIENT_OPTION_TRANSLATION_SAMPLE`

No profitable or production-ready strategy is claimed. Holdout remains sealed. Keep this PR draft, open and unmerged.
