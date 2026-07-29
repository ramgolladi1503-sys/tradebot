# Module Robustness Ranking Audit v1

Reproduce from the isolated worktree:

```bash
cd /Users/madhuram/tradebot-module-robustness-ranking-audit-v1
/opt/anaconda3/bin/python scripts/generate_module_robustness_ranking_audit.py
pytest -q tests/test_dashboard_advisory_ranking_source.py tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_feed_truth_audit.py
```

This is an audit-only evidence pack. It does not call brokers, place orders, alter strategy thresholds, or modify runtime configuration.
