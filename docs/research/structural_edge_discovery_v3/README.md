# Structural Edge Discovery V3

Research-only buy-CE / buy-PE discovery pipeline. It inventories local data, builds canonical completed-bar sessions, emits event and feature warehouses, labels frozen outcomes, generates simple interpretable candidates, runs negative controls, robustness checks, chronological walk-forward/holdout reporting, and an independent audit.

Run:

```bash
python scripts/run_structural_edge_discovery_v3.py
python scripts/audit_structural_edge_discovery_v3.py research/structural_edge_discovery_v3
```

Safety boundaries:

- No broker APIs.
- No order actions.
- No production strategy registration.
- No live, feed, risk, dashboard, deployment, credential, or config changes.
- Option tradability remains blocked unless trusted continuous contract, strike, expiry, bid/ask, and timestamp provenance are available.

