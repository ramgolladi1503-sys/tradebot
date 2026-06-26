# Entropy Truth Soak Readiness Validation

## Run Context
- **Market Status:** CLOSED
- **Live Paper Soak:** NOT PERFORMED (This is only an off-hours readiness validation)
- **Time of Run:** 2026-06-26 Off-Hours

## Executive Summary
This report summarizes the readiness of the `qa/live-paper-soak-entropy-truth-validation` infrastructure. Because the market is currently closed, a full live paper soak cannot be run. No fake evidence has been synthesized, and no live execution took place. The artifact validation analyzer (`scripts/analyze_entropy_truth_soak.py`) successfully passes on zero-cycle offline data without false positives.

## Final Verdict
**OFFHOURS_READY_ONLY** / **INCONCLUSIVE_FEED_NOT_STABLE**

*A live soak is still strictly required during market hours to obtain SOAK_PASS.*

## Analyzer Hardening
The artifact validation analyzer (`scripts/analyze_entropy_truth_soak.py`) has been hardened to support PR #609 truth-contract fields alongside legacy fields.

**Supported Field Aliases:**
- **Entropy:** `market_entropy_raw`, `regime_entropy`, `entropy`, `raw_entropy`
- **Normalized Entropy:** `market_entropy_normalized`, `regime_entropy_normalized`, `normalized_entropy`
- **Market Uncertainty:** `market_regime_uncertain`, `is_uncertain`, `entropy_too_high`
- **Quote Age:** `quote_age_sec`, `quote_age_seconds`, `option_ltp_age_sec`, `option_ltp_age_seconds`, `tick_age_sec`
- **Top Opportunity Buckets:** `display_bucket`, `bucket`, `ranking_bucket`, `ui_bucket` -> mapping to `TOP_OPPORTUNITY`

**Critical Violation Rules:**
- Bad feed candidate in Top Opportunities (exits 1)
- Bad feed candidate with `execution_ok=true` (exits 1)
- Quote age > 2.0s with `score_eligible=true` (exits 1)
- Invalid probability vector with `market_regime_uncertain=false` (exits 1)
- Active candidate is missing both raw and normalized entropy fields (exits 1)
- Active candidate is missing `data_quality_state` and no equivalent feed state can be inferred (exits 1)

