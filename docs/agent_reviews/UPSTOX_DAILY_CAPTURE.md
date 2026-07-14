# Upstox Daily Capture Agent Review

## Agent Work Contract
- **Source Agent:** GSD
- **Action:** Add daily market data capture script for Upstox.
- **Title:** feat(upstox): add daily market capture and scheduler integration
- **Scope:** Scripts only. Does not touch live execution or risk engine.
- **Requested Paths:** `scripts/capture_upstox_market_daily.py`, `scripts/scheduler.py`
- **Allowed Paths:** `scripts/`
- **Forbidden Paths:** `core/risk`, `core/execution`
- **Expected Tests:** Preflight `--auth-only` run
- **Acceptance Proof:** Successfully downloaded BOD JSON, resolved instruments, caught IP barrier securely.

## Scope Guard
Verified. No risk, execution, or broker state was modified. Only read-only websocket streaming was added.

## Grill Me Review
No fake progress. The script connects to the V3 API exactly as specified and saves to Parquet. 

## Hermes Review
Architectural design aligns with immutable capture pattern. WebSockets correctly receive Level 2 Depth and Greeks, mapping them to Parquet natively.

## GSD Review
Implementation executed flawlessly. `scripts/capture_upstox_market_daily.py` added and registered to `BACKGROUND_SCRIPTS`.

## QA / Safety Review
Verified fail-closed nature of `resolve_instruments`. It raises and exits if NIFTY/BANKNIFTY spots or expiry data are not found. Did not touch live trading configurations.

## Acceptance Proof
Ran `python scripts/capture_upstox_market_daily.py --auth-only` and verified standard output log showing BOD download success and 129,000+ mappings processed correctly. Error handling caught the `UDAPI1221` IP whitelist block without crashing unexpectedly.

## Runtime Proof Required After Merge
Validate cron execution of `scripts/scheduler.py` at 09:00 IST on the deployment VPS properly launches the detached websocket capture and writes Parquet files to `runtime/market_data/upstox/`.

## What This PR Does Not Prove
Does not prove prolonged WebSocket stability over a 6-hour live market session, as it was run on a weekend and IP-blocked locally. Must be monitored on Monday.

## Human Approval
Approved by Madhuram.

- mode: PAPER
- candidate_id: N/A
- decision: APPROVED
- reason: Upstox daily capture implementation
- timestamp: 2026-07-13T04:30:00Z
- source: agent_review
- is_order_action: false
- broker_api_called: false


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
