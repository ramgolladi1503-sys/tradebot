# Upstox Daily Live Market Capture & Post-Market Stitching Pipeline

## 1. Overview
The Upstox Daily Live Capture Pipeline provides an automated, crash-resilient system for recording full-depth market tick data across major Indian spot indices and their active options chains.

The pipeline captures:
1. **Spot Indices**: `NIFTY 50`, `BANKNIFTY`, `SENSEX`.
2. **Options Chains**: Dynamic ATM $\pm 10$ strikes (CE & PE) for the nearest expiry across all three indices (126 contracts).
3. **Closing Auction Session (CAS)**: Captures continuous market ticks through **15:40:59 IST**.
4. **Post-Market Ingestion**: Automatically stitches all atomic Parquet chunks into a unified master dataset and fetches official 1-minute historical OHLCV index candles at **15:41:00 IST**.

---

## 2. Architecture & Data Flow

```
+-------------------------------------------------------------+
|                  08:58 AM IST: Launch                       |
|   LaunchAgent / Cron executes run_daily_upstox_pipeline.sh  |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               Instrument Master & Strike Resolution         |
|   - Fetches Upstox instrument definitions                   |
|   - Queries spot prices (NIFTY, BANKNIFTY, SENSEX)          |
|   - Selects ATM +/- 10 CE/PE strikes for nearest expiry     |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|          Market Hours: Live WebSocket Streaming             |
|   - Upstox MarketDataStreamer V3 in Full Mode               |
|   - 60-Second Atomic Parquet Chunks written to disk         |
|   - Full 5-Level Bid/Ask Depth, Volume, OI, LTP             |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|          15:41 PM IST: Post-Close Master Stitching          |
|   - Deduplicates and sorts all daily chunks by timestamp    |
|   - Saves upstox_full_ticks_YYYYMMDD_stitched.parquet       |
|   - Ingests official 1m candles into indices_1m_YYYYMMDD.pq |
|   - Emits stitching_summary_YYYYMMDD.json audit report      |
+-------------------------------------------------------------+
```

---

## 3. Storage Layout & Schema

### Directory Layout
```text
/Volumes/TradeBotData/live market capture/YYYY-MM-DD/
├── chunks/
│   ├── chunk_YYYYMMDD_<timestamp_ms>.parquet
│   └── ...
├── upstox_full_ticks_YYYYMMDD_stitched.parquet
├── indices_1m_YYYYMMDD.parquet
└── stitching_summary_YYYYMMDD.json
```

### Full Tick Parquet Schema
| Column | Type | Description |
| :--- | :--- | :--- |
| `ts` | `float64` | POSIX Epoch timestamp in seconds |
| `token` | `string` | Upstox Instrument Key (e.g. `NSE_INDEX\|Nifty 50`, `NSE_FO\|47316`) |
| `symbol` | `string` | Human-readable trading symbol (e.g. `NIFTY 23900 PE 15 SEP 26`) |
| `ltp` | `float64` | Last Traded Price |
| `bid` | `float64` | Best Bid Price (Level 1) |
| `ask` | `float64` | Best Ask Price (Level 1) |
| `vol` | `float64` | Cumulative volume |
| `oi` | `float64` | Open Interest |
| `depth` | `string` | JSON serialized 5-level bid/ask depth (`{"bids": [...], "asks": [...]}`) |

---

## 4. Operational Commands

### Manual Run
```bash
# Execute daily live capture & stitching
bash scripts/run_daily_upstox_pipeline.sh

# Re-stitch a specific historical date
python3 scripts/stitch_today_market_data.py --date 2026-09-16
```

### Automated Scheduling
- **LaunchAgent**: `~/Library/LaunchAgents/com.tradebot.upstox.pipeline.plist` (Scheduled at `08:58 AM IST` Mon-Fri).
- **Crontab**: `58 8 * * 1-5 /bin/bash /Users/madhuram/tradebot/scripts/run_daily_upstox_pipeline.sh`
