# Source and License Audit

**Date:** 2026-11-02
**Investigation:** RBFN NIFTY Historical Options & Level Replication
**Governance:** Aixion Agent OS / TradeBot Safe Research Protocol

## 1. Upstream Data Source Permissions & Licensing

### A. HuggingFace: `rissin/nse-options-intraday`
- **Declared License:** `other` (Non-standard open/research license).
- **Provenance:** Derived from Upstox API 1-minute intraday OHLC captures across Indian derivatives markets.
- **Data Coverage & Completeness:**
  - NIFTY intraday starts from October 1, 2024 (pre-October 2024 is unavailable).
  - 2026 data covers January 1, 2026 through July 21, 2026 (partial year).
  - Null fields: `oi` (intraday open interest) is null; `settle_price` is null; Greeks and bid/ask quotes are absent.
- **Handling Protocol:**
  - Raw Parquet and uncompressed CSV records MUST NOT be committed to git, pushed to remote repositories, or distributed publicly.
  - Excluded in `.gitignore` under `research/rbfn_options/data/`.
  - Content hashes and schemas are recorded for reproducibility.

### B. GitHub: `technovusin/nifty50-historical-data`
- **Declared License:** MIT License.
- **Provenance:** 1-minute NIFTY 50 spot OHLCV data fetched via broker API.
- **Validation:** Timestamps verified as Asia/Kolkata (IST), bar-start convention. Cross-checked with existing TradeBot daily opening and closing levels.

## 2. Proprietary Level Attribution Audit (OptionMate)
- Ground-truth timestamped morning levels from OptionMate are **not present** in the repository or local volumes.
- In accordance with the non-negotiable research rules:
  - The independent RBFN model's five predicted levels (`lower_2`, `lower_1`, `trend_decider`, `upper_1`, `upper_2`) are explicitly documented as **independent algorithmic projections**.
  - No claim of "matching" or "duplicating" OptionMate's proprietary system is permitted.
  - The reverse engineering fidelity metric is certified as **`NOT_MEASURABLE`**.
