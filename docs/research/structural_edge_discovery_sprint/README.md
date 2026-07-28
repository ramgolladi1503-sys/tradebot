# Structural Edge Discovery Sprint

This is a research-only large hypothesis sprint built on the committed V3 campaign artifacts. It generates causal, completed-bar, human-readable buy-CE / buy-PE hypotheses, screens them cheaply, replays only the surviving subset through cost, concentration, controls, walk-forward, and holdout checks, and exports AlgoTest candidates only if they survive every gate.

Run:

```bash
python scripts/run_structural_edge_discovery_sprint.py --raw-target 25000 --replay-limit 250
```

No production, broker, feed, risk, execution, dashboard, credential, or deployment paths are modified.

