# Captured corpus recheck — 2026-10-03

**Purpose:** read-only evidence check for Issues 7/8 and campaign source-authority gates.
**Repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`.
**Authority:** inspection only; no live process, broker, order, or captured-file mutation.

## Oct. 1 session CAS artifacts

Session root: `/Volumes/TradeBotData/sessions/session_2026-10-01/2026-10-01/meg-live-2026-10-01-7093d7976e50-f830c2be2fb0/`.

`cas_session_heritage.json` declares `status=EMPTY`, `process_gap.status=UNKNOWN`, and `process_gap.reason=NO_VERIFIED_PRIOR_RUN_INTERVAL`. The 09:15 primitive has `EXPIRED_NO_CURRENT_CAPTURE`; 10:00 was `WAITING_FOR_TARGET`. There are no inherited references or prior-run coverage. Both persisted primitive attempts are `BLOCKED`; their source event IDs, event payloads/hashes, receive timestamps, source timestamps, target epochs, and prices are null. These artifacts preserve the observed lack of authority; they do not establish why the prior interval was unavailable.

## Captured market files

| File | SHA-256 | Rows | Schema / relevance |
|---|---|---:|---|
| `/Volumes/TradeBotData/live market capture/2026-10-01/upstox_full_ticks_20261001_stitched.parquet` | `c09998bf1807d4d8bc28bd3de5d4d56748269b30eabc5653ad4e8b2b8c4c5d1c` | 3,796,552 | `ts: double`, `token: string`, `symbol: string`, `ltp/bid/ask/vol/oi: double`, `depth: string`; no source event ID, source payload hash, or distinct receive timestamp columns. |
| `/Volumes/TradeBotData/live market capture/2026-10-01/indices_1m_20261001.parquet` | `98701ad9ea24647d45204db19c65440625c8b02c3a50cab852815397d84cc80a` | 1,500 | Timestamped index OHLCV/OI; not exact futures-contract or source-event authority. |
| `/Volumes/TradeBotData/live market capture/2026-10-01/stitching_summary_20261001.json` | `982a2ae409347aa4a17f015d693abb5f848854469012294c66128d9507552044` | n/a | 389/389 chunks valid, 3,796,552 ticks, 167 unique tokens; records stitching, not per-event lineage. |

Parquet row order or a hash-derived synthetic identifier cannot supply the missing original event/receive-time authority under the Issue 8 contract. The spot index file cannot establish the prior exact NIFTY futures identity/close or verified 200-session ancestry required by Issue 7. Therefore these useful replay/reference files do not close Issues 7/8 source-authority gates. Do not infer missing values as zero or reconstruct CAS from OHLC.

## Disposition

- Issue 7 positive source/manifest/calendar authority: `UNKNOWN`.
- Issue 8 prior source-event-bound CAS interval: `UNKNOWN`; exact live run artifacts independently show EMPTY/UNKNOWN and null lineage.
- Offline deterministic replay remains allowed for behavior tests, but synthetic IDs/fixtures are not historical source proof.


## Oct. 1 captured feed-block state

Read-only cross-check covered all four run directories under `/Volumes/TradeBotData/sessions/session_2026-10-01/2026-10-01/`. In three run-matched `feed_health_truth_latest.json` / `feed_runtime_latest.json` pairs, the latest health payload contains `global_feed_unhealthy` and `runtime_state_unsafe`; the paired runtime says `canonical_feed_state=RECOVERY_BLOCKED`, `state=RESTART_REQUIRED`, and blockers `WS1006_PROCESS_RESTART_REQUIRED` plus `RECOVERY_BLOCKED`, while `ws_connected=true`. One of those three also reports `OPTION_TICKS_UNVERIFIED` and `NO_SUBSCRIBED_OPTIONS`. The fourth run is `AUTH_BLOCKED` with websocket disconnected and missing LTP/depth ages. All four `candidate_decisions.jsonl` files are empty.

This narrows the captured global-block state: at the saved snapshots, a terminal recovery block (three runs) or auth/transport block (one run) was explicit; local stale-option observations are also present in three runs. The originating transport/auth failure and any hypothetical unrelated candidate path remain unknown. Since candidate decisions are empty, this evidence does not prove a candidate was locally blocked or incorrectly suppressed. It does not justify bypassing the fail-closed global recovery/auth state.

Run-matched artifact hashes (SHA-256):

| Run suffix | `feed_health_truth_latest.json` | `feed_runtime_latest.json` | `candidate_decisions.jsonl` |
|---|---|---|---|
| `7093d7976e50-f830c2be2fb0` | `8a55352364c71c4477cb3e882f425fcec17ae8194fa09f3d4104de63805a3faa` | `31525d02e80e2afdd87cb6a7e96833937744a65d1e1bf89855b799455b97637d` | empty (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |
| `79b96c5cedc7-49749d452028` | `763e6bc7f33b6c217c1f3dc9e502af3640f9733fcd0f4ab51fa38f93dbe58632` | `1ea222fabc07ed36a4e5405b65e959a8f5787ff8a376f8400d4f7b48582e4491` | empty (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |
| `98670a53e299-8cf253a5738e` | `b84f036925b4b57abc20b7e4219232e8fcad3c130b2419e50aac99dd431150f4` | `497988519a4ac4d0213fa44e1713f8d8fd63e3588965783fc6cd69c444e29412` | empty (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |
| `f17dec8af4fb-e9c85f7fda19` | `4bf9ff89259b8ffa4ad8e7a12087afed072fe265a90339acf19c08ada80bce28` | `bb19585423fc9f7de73f6c29c0c70bcc727775688132530f23dbb46d32414e4c` | empty (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`) |

## Sep. 30 prior-session replay/reference candidate

Read-only inspection found a prior-day stitched capture:

`/Volumes/TradeBotData/live market capture/2026-09-30/upstox_full_ticks_20260930_stitched.parquet`

- SHA-256: `107755a4afa76f84e269d4169bdd56dc31f6347d610fa521b0b55e06ed4e0dfc`
- Rows: `3,689,091`
- Schema: `ts: double`, `token: string`, `symbol: string`, `ltp/bid/ask/vol/oi: double`, `depth: string`
- Matching summary: `/Volumes/TradeBotData/live market capture/2026-09-30/stitching_summary_20260930.json`
- Summary SHA-256: `26e2b435478ab5249da920a89db9988a3ec3f5dd82036f9ffc14882cdf0a6302`
- Summary reports 389 valid chunks, 3,689,091 ticks, and `stitched_at_utc=2026-09-30T10:11:42.832006+00:00`.
- A full-column scan found no symbols containing `FUT`.
- Like the Oct. 1 stitched capture, the schema has no original source-event ID, source-payload hash, or distinct receive timestamp.

This is usable as a replay/reference dataset only. It does not provide an exact NIFTY futures instrument/15:29 close or the source and calendar lineage needed for the T-1 prerequisite contract. Do not substitute spot/index or option data, infer a contract from token order, or synthesize event identifiers.

## Issue 7 disposition after prior-day capture check

The September 30 capture does not close the Issue 7 positive-source gate. Keep `UNKNOWN_T1_SOURCE_AND_MANIFEST_AUTHORITY_NOT_ESTABLISHED`, keep the existing loader fail-closed, and do not stage derived values from this file. The remaining limitation is source authority, not lack of replay data.

## Additional bounded futures inventory check — 2026-10-03

Read-only inspection of `/Volumes/TradeBotData/antigravity_upstox_data_acquisition_research_unblock_v1_20260829/NIFTY_FUTURES_CONTRACT_INVENTORY.csv` found 23 NIFTY futures contract metadata rows, with expiry dates from `2024-10-31` through `2026-08-25`. SHA-256: `a6f391bbcece00582d09cf8de07f02b22845aabe2cc7ff1c967d81e41ca02b46`. Columns identify contracts and exchange tokens but contain no market bars, source-event IDs, event timestamps, or prices. The inventory has no contract entries past August 2026 and cannot directly establish the exact September 30 15:29 futures bar or its source lineage. It does not close Issue 7's required T-1 evidence. No files on the data mount were modified.

## Additional acquired futures-data report recheck — 2026-10-03

Read-only inspection of `/Volumes/TradeBotData/antigravity_upstox_data_acquisition_research_unblock_v1_20260829/FINAL_REPORT.json` (SHA-256 `e62107d74c78612f85dd2bd65c0e99cc3172d2bebdfeafe4c7e4f06cc78748e8`) and its sync metadata found a report claiming 506,423 NIFTY futures 1-minute rows across 516 sessions, ending `2026-08-25`; the spot/futures sync metadata claims 193,180 rows and 516 sessions through the same date. `SPOT_FUTURES_SYNC_MANIFEST.json` SHA-256 is `06d9c5d59d8dddbf5a54d4e568c0259f0b779840c04e776cc136cb7cdf85579d`; its contract states exact timestamp joins and near-month selection. `SPOT_FUTURES_SYNC_AUTHORITY.json` SHA-256 is `a77b8642aff547d22d2eae7a11e9e4ba9c7e603fd7db2a9fa2afaf1b1ae01a2f`; `NIFTY_FUTURES_CONTRACT_INVENTORY.csv` SHA-256 is `a6f391bbcece00582d09cf8de07f02b22845aabe2cc7ff1c967d81e41ca02b46`.

Limits are material: the report records `SOURCE_SHA=UNKNOWN`; the acquisition directory contains no parquet payload; its date range ends over a month before the required 2026-09-30 T-1 contract/bar. The separate staged live capture on 2026-09-30 still contains no futures symbols. These hashed metadata files establish only what the acquisition report claims. They do not provide verifiable content, target-date prices, contract identity, source-event lineage, or a staged manifest consumed by the live prerequisite gate. Issue 7 positive authority therefore remains `UNKNOWN`; do not use the dataset report to synthesize or stage T-1 inputs.


## Registered canonical futures corpus target-date payload check — 2026-10-03

The mounted V3 source registry labels the legacy aligned NIFTY spot/futures source as `2024-2026`, but its actual quality table records a maximum timestamp of `2026-07-28 15:29:00+05:30`. Read-only PyArrow scans of both named aligned payloads found no row for session date `2026-09-30`:

| Payload | SHA-256 | Rows | Actual session range | Rows for 2026-09-30 |
|---|---|---:|---|---:|
| `/Users/madhuram/tradebot/data/research/nifty_futures_alignment_v1/NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet` | `2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9` | 185,681 | 2024-07-26 to 2026-07-28 | 0 |
| `/Volumes/TradeBotData/NIFTY_SPOT_FUTURES_ALIGNED_V2_repaired.parquet` | `0108b00bcf62f2b42621fb3b3919b69d3faf6bc362776232c1faff8131107f9a` | 185,680 | 2024-07-26 to 2026-07-28 | 0 |

The V3 source-registry SHA matches the repo payload. Its data-quality row records one invalid OHLC row, unknown off-session-row count, and volume/OI semantics limited. Contract and DTE fields exist in schema but do not establish raw acquisition provenance. Combined with the earlier complete symbol scan of the named Sep. 30 stitched capture (no FUT symbols), neither payload supplies the required Sep. 30 15:29 futures row.

**Disposition:** this closes the question for the named registered/repaired payloads, not for every possible unregistered external source. Preserve `UNKNOWN_T1_SOURCE_AND_MANIFEST_AUTHORITY_NOT_ESTABLISHED`, retain fail-closed prerequisite loading, and do not fill the gap from spot/index or a different date. No market-data files were changed.
