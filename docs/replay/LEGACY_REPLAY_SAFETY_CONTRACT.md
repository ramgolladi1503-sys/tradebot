# Legacy Replay Safety Contract

## Mandatory Guarantees
1. `core.kite_client.KiteClient.submit_order` MUST be mocked.
2. `physical_order_calls == 0` MUST be asserted after every execution frame.
3. Fallbacks (`PLANNING_NO_SIGNAL_FALLBACK_ENABLE` and Quote Fallbacks) MUST be explicitly disabled.
4. Execution mode MUST be forced to `PAPER` internally despite any user configuration.
5. All live WebSocket inputs (`depth_ws`) MUST be explicitly skipped or mocked out to prevent state contamination.

## Prohibited Behaviors
- The replay tool MUST NOT create mock `Trade` or `market_data` intermediate dictionary objects by hand.
- The replay tool MUST NOT mutate strategy or threshold configurations unless intentionally requested via a flag.
- The replay tool MUST NOT overwrite or alter existing physical audit trails or credential files.
