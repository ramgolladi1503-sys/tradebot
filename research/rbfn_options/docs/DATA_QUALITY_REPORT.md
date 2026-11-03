# Phase 2: Data Quality & Integrity Report

**Date:** 2026-11-02
**Target Scope:** NIFTY 50 Index Spot 1-Minute & NIFTY CE/PE ATM Options 1-Minute Candles (2024–2026)
**Evaluation Grain:** `(timestamp, expiry, strike, option_type)`

## 1. Summary Metrics

- **Total Selected ATM Candidate Contracts:** 888 (61 pairs in 2024, 248 pairs in 2025, 135 pairs in 2026).
- **Total Option Bars Evaluated:** 332,994 bars.
- **Total Spot Bars Evaluated:** 262,833 bars across 704 sessions.
- **Options Intraday Session Coverage:** 444 unique trading sessions (2024-10-01 to 2026-07-21).

## 2. Gate Verification Checklist

| Quality Check | Observed Value | Gate Threshold | Status |
| :--- | :--- | :--- | :--- |
| **Duplicate Option Bars** | 0 | 0 | **PASS** |
| **Duplicate Spot Bars** | 0 | 0 | **PASS** |
| **Expiry < Trade Date** | 0 | 0 | **PASS** |
| **Invalid Option Candles** | 0 (`high >= max(o,c,l)` and `low <= min(o,c,h)`) | 0 | **PASS** |
| **Invalid Spot Candles** | 0 (`high >= max(o,c,l)` and `low <= min(o,c,h)`) | 0 | **PASS** |
| **Non-negative Prices** | 100% positive | All > 0 | **PASS** |
| **Point-in-Time Contract Selection** | Selected strictly at 09:19 using completed 09:15–09:19 bars | No lookahead | **PASS** |
| **2026 Holdout Sessions** | 135 trading sessions (Jan 1 to Jul 21, 2026) | >= 1 | **PASS** |
| **Pre-2026 Training Sessions** | 309 trading sessions (Oct 1, 2024 to Dec 31, 2025) | >= 30 | **PASS** |

## 3. Known Data Limitations & Provenance Notes

1. **Intraday Open Interest (`oi`) & Greeks:** Intraday OI is null and Greeks are unobserved in the raw vendor source. No synthetic OI or Greek values were fabricated.
2. **2026 Date Coverage:** The upstream Upstox dataset ends on July 21, 2026. Therefore, out-of-sample holdout testing evaluates all available 2026 sessions (Jan–Jul 2026).
3. **Pre-October 2024 Options:** NIFTY 1-minute intraday options begin on October 1, 2024 in the upstream dataset. The 309 training sessions (618 contract-days) satisfy the sample size requirements (threshold >= 30).
