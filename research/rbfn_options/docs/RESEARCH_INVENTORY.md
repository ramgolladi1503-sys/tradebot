# Research Inventory & Data Sources

**Date:** 2026-11-02
**Investigation:** Independent RBFN Option-Premium Research & OptionMate Level Validation
**Author:** Antigravity Autonomous Research Engine
**Branch:** `feat/rbfn-nifty-options-research`

## 1. Data Sources Inventory

| Component | Source / URI | Coverage | Status / SHA-256 Pin | Licensing / Terms |
| :--- | :--- | :--- | :--- | :--- |
| **NIFTY 50 Spot 1-Min** | `technovusin/nifty50-historical-data` (GitHub) | 2024-01-01 to 2026-11-02 (704 trading sessions) | Verified, normalized to `research/rbfn_options/data/processed/nifty_spot_1min.parquet` (262,833 bars) | Open source (MIT) |
| **NIFTY Options 1-Min (2026)** | `rissin/nse-options-intraday` (HuggingFace) | 2026-01-01 to 2026-07-21 (39 row groups, 40,177,780 rows) | Downloading (~376.5 MB), ETag `b13be486dc56fadf9c4bd5eb8d1fcc30403ac4b39f1d2ba054c24adbd607d106` | Non-standard "other" license. Derived from Upstox 1-min OHLC. Raw data kept local, excluded from git. |
| **NIFTY Options 1-Min (2024)** | `rissin/nse-options-intraday` (HuggingFace) | 2024-10-01 to 2024-12-31 (~14.5M rows) | Queued (~134.4 MB), ETag `edf8d2269efc91a7451b038ea3a7e8245a0c4f03797d70d02e3660754ab73c39` | Non-standard "other" license. |
| **OptionMate Morning Levels** | Ground truth screenshots / videos / vendor feed | 2026 holdout sessions | **NOT AVAILABLE / NOT MEASURABLE** (No verifiable historical archive provided) | Reverse-engineering match cannot be claimed. Marked NOT_MEASURABLE. |
| **Statutory Cost Schedule** | Official NSE STT Schedule & Circulars | 2024-01-01 to 2026-12-31 | STT: 0.10% (sell) to 2026-03-31; 0.15% from 2026-04-01. Brokerage Rs 20/order, GST 18%, Stamp 0.003%, SEBI 0.0001%, Exch 0.0505%. | Authoritative statutory sources. |
| **Contract Lot Sizes** | NSE F&O Master Circulars | Historical by date | 50 (to 2024-04-25), 25 (2024-04-26 onwards). | Authoritative NSE F&O circulars. |

## 2. Local Volume & Repository Inventory

- Local repository `/Users/madhuram/tradebot` examined.
- Mounted volume `/Volumes/TradeBot` inspected read-only: contains live captures, historical futures, and sensex parquet files.
- Dedicated research directory established at `research/rbfn_options/`, with local data excluded via `.gitignore`.
