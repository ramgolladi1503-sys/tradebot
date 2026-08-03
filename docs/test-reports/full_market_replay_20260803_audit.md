# TradeBot Full-Market Replay Audit — 2026-08-03

- Verdict: `FULL_SESSION_REPLAY_ACCEPTED_LIVE_KITE_AND_MEG_BLOCKERS_REMAIN`
- Provider: `Upstox`
- Drive folder: `20260803`
- Files: `40`
- Rows: `10,016,996`
- Capture window: `2026-08-03T09:00:05.538508+05:30` to `2026-08-03T15:35:00.268600+05:30`
- Corpus fingerprint: `2eeb4b595280117c568c2d84fdd7b542c589eba6788c7c3b6ff68cbd34347538`
- Live broker or order action: `false`

## What this closes

| Blocker | Status | Evidence |
|---|---|---|
| `full_session_replay_corpus_available` | `CLOSED` | 40 partitions, 10,016,996 normalized rows, 09:00:05–15:35:00 IST. |
| `collector_drop_and_parse_integrity` | `CLOSED_FOR_RECORDED_UPSTOX_CORPUS` | manifest dropped_messages=0 and parse_failures=0. |
| `replay_schema_and_partition_integrity` | `CLOSED_WITH_WARNING` | One consistent 12-column schema, no missing partition, no duplicate (timestamp,instrument_key) rows, one 4.77-microsecond timestamp inversion. |
| `recorded_feed_recovery_after_interruptions` | `PARTIALLY_CLOSED_FOR_REPLAY` | Two feed-wide interruptions >10 seconds and subsequent recorded recovery; this does not prove TradeBot/Kite recovery state. |

## What remains open

| Blocker | Status | Why replay cannot close it |
|---|---|---|
| `kite_subscription_registry_truth` | `OPEN_REQUIRES_LIVE_KITE_EVIDENCE` | Parquet has actual Upstox instrument keys only; it has no expected subscription set, ACKs, request generation, or Kite registry state. |
| `kite_post_mode_full_packet_delivery` | `OPEN_REQUIRES_LIVE_KITE_EVIDENCE` | Normalized replay has no Kite packet-mode or subscription-mode field. |
| `nifty50_constituent_bar_and_meg_traversal` | `OPEN_REQUIRES_LIVE_OR_NSE_EQ_REPLAY` | The corpus contains no NSE_EQ constituent keys; it cannot produce the 40+ constituent breadth contract. |
| `pr763_governed_live_session` | `OPEN` | Replay cannot replace a fresh read-only market-session run from the certified PR #763 implementation SHA. |

## Corpus integrity

- Manifest messages: `156,927`.
- Manifest dropped messages: `0`.
- Manifest parse failures: `0`.
- Manifest reconnects: `3`.
- Manifest coverage keys: `722`.
- Actual coverage keys: `722`.
- Coverage matches manifest: `true`.
- Exact duplicate `(ts, instrument_key)` rows: `0`.
- Timestamp order violations: `1`.
- Warning: one capture timestamp moved backward by `4.768` microseconds; no duplicate row resulted.

## Instrument coverage

| Prefix | Keys | Rows |
|---|---:|---:|
| `NSE_FO` | 484 | 5,460,924 |
| `BSE_FO` | 234 | 4,296,194 |
| `NSE_INDEX` | 3 | 236,237 |
| `BSE_INDEX` | 1 | 23,607 |
| `NSE_EQ` | 0 | 0 |

Because `NSE_EQ` is absent, this replay cannot build or certify the 40-plus NIFTY constituent breadth contract required by the Market Event Graph.

## NIFTY feed cadence

- NIFTY rows: `94,568`.
- Median inter-arrival: `0.285` seconds.
- P95 inter-arrival: `0.375` seconds.
- P99 inter-arrival: `0.599` seconds.
- Gaps over 5 seconds: `4`.
- Gaps over 10 seconds: `2`.
- Maximum gap: `31.930` seconds.

## Recorded interruption recovery

| Gap | Start IST | End IST | Pre-gap active keys | Recovered within 120s | P50 recovery | P90 recovery | Max recovery |
|---:|---|---|---:|---:|---:|---:|---:|
| 31.777s | 2026-08-03T11:32:25.124979+05:30 | 2026-08-03T11:32:56.901613+05:30 | 648 | 648 | 0.246s | 6.955s | 6.955s |
| 16.443s | 2026-08-03T11:30:59.461748+05:30 | 2026-08-03T11:31:15.904803+05:30 | 676 | 676 | 0.527s | 26.118s | 107.952s |
| 5.133s | 2026-08-03T10:06:48.673442+05:30 | 2026-08-03T10:06:53.806766+05:30 | 676 | 670 | 0.754s | 13.293s | 114.575s |

The two largest interruptions were feed-wide across NIFTY, BANKNIFTY, India VIX, SENSEX and derivative keys. The recording resumed afterward. This is replay recovery evidence, not proof that TradeBot's Kite subscription registry or recovery state machine was correct.

## Decision

- Leave the failed multi-strategy portfolio out of the first shadow campaign.
- Retain a single Market Event Graph advisory-only campaign.
- Use this corpus as the full-session replay and persistence/stress input.
- Do not use it to close Kite subscription-registry truth, Kite FULL packet delivery, or live constituent breadth.
- The remaining mandatory proof is a fresh governed PR #763 read-only market session with NSE constituent subscriptions.

## Claim boundaries

- This evidence validates a recorded Upstox full-session replay corpus, not a live Kite WebSocket session.
- Capture timestamps are available; no exchange/source timestamp field is present.
- No expected-subscription registry, subscription ACK, reconnect generation, or packet-mode field is present.
- No NSE cash-equity constituent keys are present, so Market Event Graph breadth cannot be certified.
- Numeric derivative instrument keys cannot be mapped to strike, expiry, CE, or PE without an external instrument master.
- No candidate lineage, ranking, approval, execution, fill, or order evidence is present.
