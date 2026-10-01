# WebSocket recovery matrix

| Proof case | Coordinator result | Evidence |
|---|---|---|
| No proof / resumed ticks only | `RECOVERY_CLEAR_REJECTED`; recovery state remains active | Focused coordinator and runtime-caller tests passed |
| Missing/extra required identity | Remains blocked | Focused proof mutation test passed |
| Excessive/invalid per-identity gap | Remains blocked | Focused proof mutation test passed |
| Rebuild missing/unknown | Remains blocked | Focused proof mutation test passed |
| Exact identities + timestamps/gaps + rebuilt state + bounded health window | Coordinator can clear and appends in-memory resolution record | Focused synthetic unit test passed |
| Current runtime caller supplies complete causal proof for eligible recoverable peer drop | Runtime builder now assembles proof from captured subscription replay and critical underlying tick receipts, option verification, freshness, and the configured healthy window | Focused and expanded offline recovery suites pass; local API-call evidence is not broker acknowledgement |
| Restart subscription/option-tick verification alone | `FEED_RECONNECT_RECOVERY_CLEAR_DENIED`; restart-required blocker remains set | `tests/test_kite_depth_restart.py` plus coordinator/stability selection: 125 passed |
| Partial-activity stable ticks while restart-required blocker is active | Runtime stays `RECOVERY_BLOCKED`; blocker is preserved in telemetry | Expanded recovery selection: 125 passed |
| Durable cross-process resolution record | Not added | UNKNOWN; no incident artifact rewrite/delete performed |

The runtime proof builder now records observable progress in both snapshot producers. Resolved critical underlying identities are used for continuity gaps; exact current subscription sets are separately reconciled, while candidate option freshness remains enforced at its existing exact candidate boundary. Eligible recoverable peer drops may clear only after all checks and a continuous configured healthy window. Evidence proves the local subscribe/mode calls returned, not broker-side acknowledgement. Process-restart-required terminal blockers remain uncleared, and the coordinator resolution history remains process-local with only optional append-only forensic persistence. Offline tests do not establish full real-callback race behavior or production operational readiness.
