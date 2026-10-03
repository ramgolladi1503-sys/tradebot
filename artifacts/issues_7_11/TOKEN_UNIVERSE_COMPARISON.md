# Token-universe preservation comparison

- Campaign baseline SHA: `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
- Current source SHA: `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95` (working tree contains only the campaign diff)
- Comparison: pre-campaign `HEAD` blob bytes against current working-tree bytes.
- Result: configuration, launch-plan implementation, and pinned observation-universe manifest are byte-identical.

| Authority input | SHA-256 at baseline | SHA-256 current | Equal |
|---|---|---|---|
| `config/config.py` | `b1b23141428530b8e51f98f73810f5ecf77df49187d9d92538fb7cc71f8ba950` | `b1b23141428530b8e51f98f73810f5ecf77df49187d9d92538fb7cc71f8ba950` | yes |
| `core/market_event_graph_live_observation_registry.py` | `c790cfb86d366bc1eeb8db868ba0d1452c040b6b6f510cd5c777b8b7014a8c1c` | `c790cfb86d366bc1eeb8db868ba0d1452c040b6b6f510cd5c777b8b7014a8c1c` | yes |
| `core/market_event_graph_live_launch_plan.py` | `39e8563cb4ca9768848bc5583825d2063668df552f056838c6d163dcd0015481` | `39e8563cb4ca9768848bc5583825d2063668df552f056838c6d163dcd0015481` | yes |
| `runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json` | `d516138b1cd8b87d16aaa06d30b5924fb42c916dd59d36de0cac961c97c404db` | `d516138b1cd8b87d16aaa06d30b5924fb42c916dd59d36de0cac961c97c404db` | yes |

The pinned observation manifest contains 50 unique constituent instrument tokens plus index token `256265` (51 observations). The launch-plan contract test covers 73 production tokens plus 51 observation tokens with one overlap, yielding 123 unique tokens, and rejects expansion to 124. These are source/fixture assertions; they do not prove the current live production token set or active subscription count.

Regression command:

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_pulse_issues_and_feed_consistency.py tests/test_market_event_graph_live_observation_registry.py tests/test_market_event_graph_live_launch_plan.py tests/test_depth_subscription_tokens.py tests/test_depth_persistence_batching.py tests/test_kite_depth_restart.py tests/test_tick_subscription_plan_includes_indices.py tests/test_subscription_truth_contract.py tests/test_pr_feed_10_subscription_budget_policy.py tests/core/test_token_coverage_threshold.py tests/test_check_option_pipeline_health.py`

Result: **111 passed, 1 warning in 11.70s**.

Disposition: repository-defined token policy and pinned observation-universe bytes are unchanged by this campaign, and their offline topology/budget regressions pass. Captured/live active-universe parity remains `UNKNOWN`; no 53-token historical observation or synthetic 123-token fixture is promoted to live evidence.
