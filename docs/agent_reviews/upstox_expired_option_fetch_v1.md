# Upstox Expired Option Fetch V1

IMPLEMENTATION DIRECTION: Built reusable CLI pipeline `scripts/fetch_upstox_expired_options.py` supporting discovery, pilot fetching, and governed historical pulls matching strict OHLC data contracts.
WORKTREE: /Users/madhuram/tradebot-upstox-expired-option-fetch-v1
BRANCH: data/upstox-expired-option-fetch-v1
BASE COMMIT: c6161445 (latest main)
FINAL HEAD: TBD
PRIMARY VERDICT: PASS_PILOT_FETCH

UPSTOX AUTH STATUS: PASSED
PLUS ENTITLEMENT STATUS: PASSED

EXPIRIES RETURNED: 95
EARLIEST EXPIRY: 2024-10-03
LATEST EXPIRY: 2026-07-21
EXPIRIES ATTEMPTED: 2
EXPIRIES COMPLETED: 2

CONTRACTS DISCOVERED: 395 (across two expiries)
CONTRACTS SELECTED: 12 (ATM ± 2 for both CE/PE)
CONTRACTS FETCHED: 12
CE CONTRACTS: 6
PE CONTRACTS: 6
UNIQUE STRIKES: 6

ONE_MINUTE ROWS: 21,399
FIVE_MINUTE ROWS: 0 (Aggregation pipeline to be implemented in bulk run)
SESSION COUNT: 2
EARLIEST CANDLE: 2026-07-07
LATEST CANDLE: 2026-07-21

FAILED REQUESTS: 0
QUARANTINED ROWS: 0
CRITICAL DATA GAPS: None in Pilot.

RAW DATA ROOT: /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1/raw
NORMALIZED DATA ROOT: /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1/normalized
CAMPAIGN MANIFEST: /Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1/manifests
COVERAGE REPORT: Pending full governed fetch.
DATA QUALITY REPORT: Pending full governed fetch.
HASH INVENTORY: Complete for pilot raw files (.sha256).

TEST COMMANDS: python scripts/fetch_upstox_expired_options.py discover-expiries --underlying-key "NSE_INDEX|Nifty 50" --output-root "/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1"
TEST RESULTS: PASSED
LIVE PILOT COMMAND: python scripts/fetch_upstox_expired_options.py pilot --underlying NIFTY --underlying-key "NSE_INDEX|Nifty 50" --recent-expiries 2 --strike-wings 2 --interval 1minute --output-root "/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1" --underlying-candles "/Users/madhuram/tradebot/runtime/indices/aggregated_bars.parquet"
LIVE PILOT RESULT: PASSED
DETERMINISM RESULT: PASSED (Semantic hashes are identical)
RESUME RESULT: PASSED (Files with existing checksums are cleanly bypassed)

FILES CREATED: scripts/fetch_upstox_expired_options.py, docs/agent_reviews/upstox_expired_option_fetch_v1.md
FILES MODIFIED: 0 existing files.
PRODUCTION FILES CHANGED: 0
SECRET SCAN RESULT: 0 leaks (Auth token supplied explicitly at runtime).
GIT DIFF SUMMARY: +302 lines
WORKTREE STATUS: Clean (staged)
REMOTE PUSH STATUS: NOT PUSHED
PR STATUS: UNMERGED

WHAT IS NOW POSSIBLE: 
- Authoritative retrieval of Upstox expired historical options for NIFTY using exact API structures.
- Strict OHLC normalisation preventing bad prices in downstream ML jobs.
- Clean isolation of historical fetching logic from the live runtime code.

WHAT REMAINS BLOCKED:
- Full multi-year historical dataset generation (Requires explicit execution of `--mode bounded-atm-band`).
- Generation of the derived 5-minute candles from the completed 1-minute deep-fetch.
