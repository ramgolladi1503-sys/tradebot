# Kite Read-Only Observation Runtime v1

This composition is an observation runtime only. It uses `SIM` for execution
mode while consuming real Kite market data. It does not invoke `main.py`,
`run_live.sh`, the live broker adapter, an order router, paper fills, or order
reconciliation.

## Reused Components

- `core.auth.get_kite_credentials` and `core.auth.get_kite_client` for approved
  token resolution and harmless profile authentication.
- `core.kite_depth_ws.activate_market_event_graph_launch_plan` and
  `core.kite_depth_ws.start_depth_ws` for the existing Kite subscription,
  callback, tick/depth persistence, completed-bar, and MEG observation path.
- `core.runtime_snapshot_producer.produce_and_store_runtime_snapshots` for the
  existing runtime snapshot and canonical PR #771 authority evaluation path.
- Existing persistence worker shutdown is reached through
  `core.kite_depth_ws.stop_depth_ws`.

## Safety Boundary

The composition sanitizes inherited mode and execution flags to `SIM`, disables
the live broker adapter and paper execution, requires read-only evidence, and
rejects broker-write methods through `BrokerWriteFirewall`. The import boundary
rejects broker adapters, execution routers, order engines, and paper-fill
modules before feed startup.

The governed market-session runner invokes only
`scripts/run_kite_read_only_observation_v1.py`; there is no fallback to
`run_live.sh`.
