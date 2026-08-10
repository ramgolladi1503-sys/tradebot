# Vendor Data Sample Request Note — TradeBot / MROS

## Purpose
This document specifies the exact, low-cost sample data required to evaluate directional research feasibility before making any full dataset or tick/bid-ask depth purchases.

---

## Strategic Guidance
> [!IMPORTANT]
> We are **not** requesting full tick/bid-ask/depth data yet.
> We want to evaluate research viability on OHLC/volume lead-lag signals before purchasing large microstructure datasets or options depth infrastructure.

---

## Sample Request Priorities

### 1. Primary Request: NIFTY 50 Constituent OHLCV Sample
- **Dataset**: NIFTY 50 constituent stocks (top 10 minimum: RELIANCE, HDFCBANK, ICICIBANK, INFY, TCS, LTIM, KOTAKBANK, LT, AXISBANK, SBIN).
- **Granularity**: 1-minute or 5-minute OHLCV bars.
- **Sample Period**: 1 month (e.g., January 2024).
- **Schema Contract**: Conforming to `research/evidence/data_capability_gate_v7/schema_contracts/constituent_breadth_schema_contract.json`.

### 2. Secondary Request: NIFTY Spot + Near-Month Futures OHLCV Sample
- **Dataset**: NIFTY index spot + near-month futures continuous series.
- **Granularity**: 1-minute OHLCV bars + Open Interest.
- **Sample Period**: 1 month.
- **Schema Contract**: Conforming to `research/evidence/data_capability_gate_v7/schema_contracts/futures_basis_schema_contract.json`.

---

## Evaluation Gate
Upon receipt of the 1-month sample:
1. Run `scripts/research/data_capability/validate_constituent_breadth_sample.py`.
2. Evaluate `CONSTITUENT_INDEX_LEAD_LAG_BREADTH` in development split (first 60% of sample sessions).
3. Evaluate negative controls (Wrong Window, Symbol Permutation).
4. **Go/No-Go Decision**: Purchase full 12+ month dataset only if the 1-month sample survives negative controls with net > 10 bps directional edge.
