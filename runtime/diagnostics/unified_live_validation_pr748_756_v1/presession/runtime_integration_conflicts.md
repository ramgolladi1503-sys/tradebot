# Runtime Integration Conflicts

## config/config.py
Conflicting PRs: #748, #750. #750 owns feed-recovery config. #748 owns Market Event Graph live-source flags. Final behavior preserves #750 recovery keys and adds #748 live-source config flags. Regression: focused #748/#750 tests passed.

## core/kite_depth_ws.py
Conflicting PRs: #748, #750. #750 owns feed truth, partial recovery, VERIFYING_RECOVERY/DEGRADED_LOCAL, and ws1006 recovery. #748 owns observation token union, subscription evidence, feed session/reconnect provenance, and shadow tick routing. Final behavior uses #750 as base with #748 observation state and tick-routing hooks. Regression: 141 WebSocket/feed tests passed.

## core/candidate_pool_orchestrator.py
Conflicting PRs: #749 plus campaign observer. #749 remains sole completed-constituent producer; campaign only observes built report. Regression: constituent and campaign tests passed.

## core/runtime_snapshot_producer.py and core/opportunity_scoring.py
Conflicting PRs: #756 plus campaign observer. #756 regime semantics preserved; campaign records outputs after decisions are built. Regression: regime/scoring tests passed.

Remaining limitation: dry smoke is not live WebSocket proof and is not a formal soak.
