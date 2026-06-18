# Real Option Validation Feasibility Report

## Objective
To determine if we can replace theoretical synthetic delta/spread assumptions with pure, high-fidelity historical Option Data (Tick-by-Tick or 1-minute OHLC with Bid/Ask).

## Broker API Constraints

### 1. Zerodha (Kite Connect API)
- **Feasibility**: ❌
- **Reasoning**: Zerodha's historical API provides historical 1m data for equities and index futures stretching back years, but **aggressively purges expired option contracts** within roughly a week after expiry to save database costs. We cannot download a 3-year history of NIFTY options through the Kite Historical API.

### 2. Upstox API
- **Feasibility**: ⚠️
- **Reasoning**: Upstox historically preserves more option data than Zerodha, providing 1-minute OHLCV for expired contracts. However, their standard historical API does **not** provide historical Bid/Ask spreads. This limits our ability to do exact slippage tracking. We would have to rely on `Open` and `Close` prices, which again abstracts the spread penalty.

## Alternative Sources

### 3. NSE Archives
- **Feasibility**: ❌
- **Reasoning**: The NSE provides free, public archives of the Daily Bhavcopy. While this contains every expired contract, it only includes End-of-Day (EOD) data (Open, High, Low, Close, Settlement Price). It is completely useless for intraday execution routing, 15m signals, or minute-level execution realities.

### 4. Paid Enterprise Providers (TrueData, GlobalDatafeeds)
- **Feasibility**: ✅
- **Reasoning**: Enterprise vendors explicitly capture and sell Tick-by-Tick or 1-second snapshots of all NSE Option contracts, including Level 1 (Bid/Ask) or Level 2/3 (Market Depth) data.
- **Cost/Effort**: This data is extremely massive (hundreds of Gigabytes per year) and comes at a premium cost. Implementing it would require migrating our backtesting framework from CSV processing to a large-scale Parquet or ClickHouse database.

## Verdict
**Proceed with Paper Execution Live-Forward.**
Given the high cost and engineering overhead of acquiring 3 years of 1m Bid/Ask option data, our best strategy is to rely on our realistic synthetic execution models for historical data, and aggressively capture real option data *live-forward* using our Paper Trading Engine against the live Websocket.
