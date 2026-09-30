# T-1 authority forensics

**Verdict: BLOCKED — provenance is not established.**

The file was found only in the canonical checkout at `/Users/madhuram/tradebot/runtime/preflight/t1_prerequisites_2026-10-01.json` and remains untracked there. It was not copied into this worktree, consumed by this repair, or modified. SHA-256 observed: `4060b0d81888564bdee359e948812e9b21b181800f2b95de404d3fd5fccd6477`. Its metadata reports source `MEG_LIVE_OBSERVATION_SESSION_2026-09-30`, session date `2026-10-01`, and verified-at string `2026-09-30T15:30:00+05:30`. Keys present: `opening_drive_prev_close_1529, opening_drive_prev_contract_key, opening_drive_target_expiry, overnight_prev_daily_close, overnight_prev_sma200, session_date, source, verified_at`.

This metadata does not establish source event IDs, immutable source payload hashes, exact authoritative futures contract/bar identity, daily-close ancestry, independent source verification, or a signed/pinned producer manifest. `verified_at` is a claim in the file, not provenance proof. The repair's existing heritage loader correctly fails closed when these authorities are absent. A read-only recheck on 2026-10-01 found the same SHA-256 and the file still untracked; no contents were read or consumed.

The pre-existing heritage validation evidence says the inventory-only producer leaves values null and `BLOCKED_SOURCE_AUTHORITY`; it does not promote legacy file values. No T-1 value was printed, copied, consumed, or mutated in this continuation.

`T1_PROVENANCE_MANIFEST.json` was intentionally not created because its prerequisite condition (verified provenance) is false. No current artifact hash equality or live-session continuity claim is made.

Safety: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.

## Captured 2026-09-30 data inventory

Bounded, read-only inspection found these existing capture artifacts:

- `/Volumes/TradeBotData/live market capture/2026-09-30/stitching_summary_20260930.json` SHA-256 `26e2b435478ab5249da920a89db9988a3ec3f5dd82036f9ffc14882cdf0a6302`; it reports 389 valid chunks and 3,689,091 ticks, but contains no per-chunk content hashes or source-event IDs.
- `/Volumes/TradeBotData/live market capture/2026-09-30/upstox_full_ticks_20260930_stitched.parquet` SHA-256 `107755a4afa76f84e269d4169bdd56dc31f6347d610fa521b0b55e06ed4e0dfc`; its 129 unique symbol/token pairs include spot indices and options. No symbol contains a futures marker, so this capture does not supply the required NIFTY futures contract/bar.
- `/Volumes/TradeBotData/live market capture/2026-09-30/indices_1m_20260930.parquet` SHA-256 `d17ffdbaf674b26cf2d3c1448a997f8aea2a0d694382858bc50b888509ab24a4`; it has 1,500 rows for NIFTY 50, NIFTY BANK, India VIX, and SENSEX. It is spot-index data, not the required NIFTY futures contract evidence.
- `/Volumes/TradeBotData/sessions/session_2026-09-30/logs/token_resolution.json` SHA-256 `5df76201d78457f251b95b8f5e8ad1cd0746d211f307f4a376d96da770910539`; it records the runtime token-resolution state, but does not bind the manual T-1 file's values to source event IDs/payload hashes or provide the previous-session futures contract/bar authority.

These captures improve the negative finding: the inspected 2026-09-30 tick/spot dataset cannot reconstruct the exact NIFTY futures input required by Opening Drive. Their hashes were rechecked on 2026-10-01 and match the recorded values. They do not establish daily-close source ancestry or independently verified SMA200 provenance. T-1 remains `BLOCKED`; no provenance manifest is valid. The capture files were read only and not changed.
