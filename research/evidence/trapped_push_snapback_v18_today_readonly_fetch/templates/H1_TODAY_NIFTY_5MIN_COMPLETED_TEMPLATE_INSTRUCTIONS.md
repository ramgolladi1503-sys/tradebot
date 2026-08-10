# Manual Append Intake Template Instructions — H1 Trapped Push Snapback

## Overview
When the read-only Kite API fetch fails due to a missing access token (`missing_kite_access_token`), completed forward 5-minute NIFTY OHLC bars can be appended manually using this governed CSV template.

## Intake File Location
Place the filled CSV file at:
`research/evidence/trapped_push_snapback_v18_today_readonly_fetch/input_bars/NIFTY_5MIN_2026-08-10_COMPLETED.csv`

## Required Schema & Format
- `datetime`: Timestamp in ISO string format (e.g., `2026-08-10 09:15:00` in IST)
- `open`: Opening price (numeric)
- `high`: High price (numeric)
- `low`: Low price (numeric)
- `close`: Closing price (numeric)

## Execution Rules
- Only process completed 5-minute bars.
- Do not fabricate synthetic or fake prices.
- Once populated, run `python3 scripts/research/hypothesis_factory/validate_h1_forward_bar_intake_v18.py --input-bars ...` to validate.
