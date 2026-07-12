# Legacy Replay Runtime Trace

## Execution Flow
1. **Replay Provider Accepts Event**: `RecordedReplayEvent` is generated from JSONL.
2. **State Updates**: 
   - `core.tick_store.insert_tick` is called.
   - `core.time_utils._INJECTED_CLOCK` is advanced.
3. **fetch_live_market_data()**: Reads the replayed event naturally through `get_ltp`, pulling from `tick_store`.
4. **_legacy_live_monitoring()**:
   - `fetch_live_market_data` resolves correctly.
   - The signal generation (TradeBuilder) executes without exceptions.
   - Candidate pool and blocker logic successfully assess the state.
5. **Execution Router**: Not reached for physical orders; mocked and verified as `call_count == 0` during the test run.

## Final Decision Capture
Trace confirms the final pipeline executes flawlessly on schema-compliant datasets and terminates cleanly after `run_once=True` iteration completes.
