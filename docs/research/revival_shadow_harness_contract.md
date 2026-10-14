# Governed Revival Shadow Harness Contract

Date: 2026-09-22
Author: Recertified GSD Stage 2 Implementation
Status: REPAIRED_AND_RECERTIFIED / SHADOW_HARNESS_READY_FOR_COMMISSIONING

## 1. Operating State & Authority Isolation

The prospective shadow harness strictly enforces:
```text
read_only=true
shadow_only=true
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false

ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```

### Data Provenance & API Accountability
- `market_data_source`: Explicitly recorded as `SYNTHETIC_TEST`, `HISTORICAL_REPLAY`, `BROKER_FEED`, or `VENDOR_FEED`.
- `market_data_api_called`: `false` for unit tests / synthetic inputs; `true` only when genuine network API calls occur.
- `broker_write_api_called`: Strictly `false`.
- `order_api_called`: Strictly `false`.
- `TARGETED_WRITE_METHOD_GUARD`: Passed (rejects `place_order`, `modify_order`, `cancel_order`, `exit_order`, `post`, `put`, `delete`, `send_order`, `submit`, `execute`).
- `BROKER_WRITE_REACHABILITY`: Not independently proven (acknowledged guard boundary; order authority remains hard-coded False).

## 2. Cost Authority Status: UNVERIFIED

In accordance with strict empirical rules:
- Sourced rates (STT, NSE charges, stamp duty, SEBI turnover fees, brokerage caps) are tagged `UNVERIFIED`.
- An unverified authority returns `None` for cost calculations, causing the harness to emit `cost_drag_pts=None` and `net_pnl_pts=None` (`COST_UNKNOWN`).
- Zero-cost substitution is strictly forbidden.

## 3. Cryptographic Chain & Provenance Sealing

- Dynamic commit tracking: `head_commit_sha` is read directly from repository HEAD.
- Working-tree content hash: `working_tree_content_hash = SHA256(git diff HEAD + git status --porcelain)` ensures that uncommitted working tree modifications are cryptographically bound to the session manifest.
- Each record links to the previous: $\text{SHA256}(\text{prev\_record\_hash} + \text{canonical\_payload\_json})$.
- In-place mutation, deletion, or reordering breaks the chain and triggers an immediate assertion failure.

## 4. Candidate Reconciliation Statuses & Lifecycle Timestamps

- All prospective start boundaries are locked to `2026-09-22T04:30:00+05:30` (the actual freeze timestamp of this harness). Prior observations remain historical/discovery evidence.
- `CAND_01`: Spot statistical predictability (`close_15:29 - open_09:15` predicting `open_next_09:15 - close_15:29`). Futures translation is explicitly treated as a separate audited candidate.
- `CAND_02`: Delayed direction / gap confluence A (09:20 close entry, 10:15 close exit).
- `CAND_03`: Corrected lifecycle semantics recovered from `scripts/research/audit_reconciled_day_to_night.py` (entry at 15:25 futures close, exit at next-session 09:16 futures open).
- `CAND_04`: Low gap x low prior return (< 20th percentile cuts).
- `CAND_05` & `CAND_06`: Retained as `BLOCKED_RECONCILIATION_REQUIRED`.
