# ORB Option Bid/Ask Recoverability Inventory

Read-only local screen. No source datasets were copied, rewritten, fetched, or hashed wholesale.

- Files discovered: 5963
- Candidate universe: current certified corrected candidate universe, 2215 candidates
- Obvious local option-named Parquet files inspected: 126
- Rows scanned in those option-named files: 2618670
- Positive non-crossed bid/ask rows in those option-named files: 0
- Readable `.runtime/market_data` option-symbol rows scanned: 5812897
- Positive non-crossed option bid/ask rows in readable `.runtime/market_data` tick captures: 0
- Primary data finding: NO_LOCAL_TRUSTED_OPTION_BID_ASK
- Additional blocker: candidate ledger has no expiry/strike/CE-PE/token mapping and no exit timestamp owner.

## Known Data Areas

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`: contains underlying OHLC session files and 126 obvious option-named Parquet files under `20260709`. Those option files have `ts`, `token`, `symbol`, `ltp`, `bid`, `ask`, and `depth`, but the scan found zero positive non-crossed option bid/ask rows.
- `/Users/madhuram/tradebot/.runtime/market_data`: readable sampled tick captures expose option symbols and bid/ask columns, but zero option-symbol rows had positive non-crossed bid/ask. One corrupt/tiny Parquet file was excluded from evidence.

## Classification Boundary

No local source was promoted to candidate-level executable coverage. Zero bid/ask is not executable top-of-book, OHLC is not bid/ask, LTP is not bid/ask, and underlying bid/ask is not option bid/ask.
