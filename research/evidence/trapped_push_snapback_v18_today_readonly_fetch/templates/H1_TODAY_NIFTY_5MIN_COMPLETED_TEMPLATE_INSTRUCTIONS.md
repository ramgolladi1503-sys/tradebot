# Manual Append Intake Template Instructions — H1 Trapped Push Snapback

## Overview
When the read-only Kite API fetch fails due to a missing access token (`missing_kite_access_token`), completed forward 5-minute NIFTY OHLC bars can be appended manually using this governed CSV template.

## Intake File Location
Place the filled CSV file at:
`research/evidence/trapped_push_snapback_v18_today_readonly_fetch/input_bars/NIFTY_5MIN_2026-08-10_COMPLETED.csv`

## Required Header (DO NOT REMOVE OR EDIT HEADER)
`datetime,open,high,low,close,volume_optional,source,completed_bar,timezone`

## Warning
- **Do not leave example rows or comments in the CSV file.**
- Only completed 5-minute NIFTY bars are allowed.
- Do not include incomplete current bars (`completed_bar` must be `true`).
- Do not include orders, trades, option fills, P&L, or signals.

## Example Row (For Reference Only — Put in CSV without comments)
`2026-08-10 09:15:00,24500.0,24530.0,24480.0,24510.0,0,KITE_OR_BROKER_FEED,true,Asia/Kolkata`

## Validation Execution
Once populated, run:
`python3 scripts/research/hypothesis_factory/validate_h1_forward_bar_intake_v18.py --input-bars ... --output-audit ... --observation-date 2026-08-10`
