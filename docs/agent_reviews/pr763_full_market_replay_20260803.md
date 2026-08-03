# PR #763 Full-Market Replay Evidence — Agent Review

mode: OFFLINE_READ_ONLY
candidate_id: pr763-full-market-replay-20260803-v1
decision: FULL_SESSION_REPLAY_ACCEPTED_LIVE_KITE_AND_MEG_BLOCKERS_REMAIN
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Scope

This stacked evidence change records machine-audited findings for the 2026-08-03 full-market replay corpus. It does not modify feed, authentication, strategies, ranking, risk, execution, broker, dashboard, or PR #763 runtime behavior.

## Source evidence

Drive folder:

```text
20260803
https://drive.google.com/drive/folders/1GKI5aaYoJvomIqC-u2YFF9aQqDn6mxI6
```

Observed corpus:

```text
40 parquet partitions
10,016,996 normalized rows
722 actual coverage keys
09:00:05–15:35:00 IST
0 dropped messages
0 parse failures
3 reconnects
```

## Acceptance Proof

The corpus was streamed across all partitions and checked for schema consistency, manifest reconciliation, timestamp order, exact timestamp/instrument duplication, instrument-prefix coverage, index cadence, partition continuity, feed-wide interruption windows, and post-interruption key recovery.

A standalone reusable audit implementation was syntax-checked and its focused false-certification controls passed locally:

```text
python compilation: PASS
focused tests: 4 passed
```

The controls prove:

- no Market Event Graph breadth claim without at least 40 `NSE_EQ` keys;
- replay cannot close the governed PR #763 live-session requirement;
- interruption recovery retains missing-key truth;
- binary and absent instrument identities are normalized safely.

## Findings

Closed:

```text
FULL_SESSION_REPLAY_CORPUS_AVAILABLE
COLLECTOR_DROP_AND_PARSE_INTEGRITY_FOR_RECORDED_UPSTOX_CORPUS
REPLAY_SCHEMA_AND_PARTITION_INTEGRITY_WITH_ONE_MICROSECOND_WARNING
```

Partially closed:

```text
RECORDED_FEED_RECOVERY_AFTER_INTERRUPTION
```

Still open:

```text
KITE_SUBSCRIPTION_REGISTRY_TRUTH
KITE_POST_MODE_FULL_PACKET_DELIVERY
NIFTY50_CONSTITUENT_BAR_AND_MEG_TRAVERSAL
PR763_GOVERNED_LIVE_SESSION
```

## Truth boundary

The corpus contains `NSE_FO`, `BSE_FO`, `NSE_INDEX`, and `BSE_INDEX` keys but no `NSE_EQ` constituent universe. It also contains no expected subscription set, subscription ACK, reconnect generation, Kite packet mode, candidate lineage, ranking, approval, execution, or order evidence.

Therefore the replay is valid for full-session market-data compatibility, continuity, persistence and downstream stress. It cannot replace the fresh read-only Kite and Market Event Graph session required by PR #763.

## Final Review Verdict

```text
REPLAY_BLOCKER: CLOSED
MULTI_STRATEGY_CAMPAIGN: DEPRIORITIZED
KITE_REGISTRY_BLOCKER: OPEN
MEG_LIVE_BREADTH_BLOCKER: OPEN
BROKER_OR_ORDER_AUTHORITY: NONE
```
