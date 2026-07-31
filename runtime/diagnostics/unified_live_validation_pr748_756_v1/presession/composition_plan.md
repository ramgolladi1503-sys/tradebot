# Composition Plan - Unified Live Validation PRs #748-#756

## Scope

This branch is an isolated read-only campaign harness. It does not merge the original PR branches into `main`, does not modify those PR branches, and does not certify profitability or production readiness.

## Selected Live Constituent Producer

Selected producer: `pr_749_constituent_source_feeds_pr_748_validator_exporter`.

Reason: PR #749 owns exact current NIFTY constituent reconstruction and completed one-minute interval production. PR #748 owns launch governance, token-union provenance, and Market Event Graph validator/exporter authority. The safe composition is one producer feeding one validator/exporter chain. The campaign must not run two independent constituent interval producers, two watermarks, or two graph emitters.

## Authority Resolution

- PR #750 is authoritative for feed truth, bounded recovery verification, registry consistency, and fail-closed execution-feed readiness.
- PR #748 is authoritative for Market Event Graph launch plan, observer token union, captured metadata validation, and governed output.
- PR #749 is authoritative for NIFTY constituent manifest and completed constituent bars.
- PR #756 is authoritative for regime probability truth, feature quality, uncalibrated semantics, and regime-policy propagation.

## Conflicts

Changed-file overlap was detected in `config/config.py` and `core/kite_depth_ws.py` between PR #748 and PR #750. These are high-risk runtime/feed paths and were not auto-merged. The campaign harness is additive and records the authority decision instead of resolving conflicts by branch order.

## Research Boundary

PRs #751, #752, #754, and #755 are forward-observation only unless their exact frozen survivor/model artifacts are proven. PR #753 is offline-only and not applicable to the live runtime.

## Safety

The harness writes append-only JSONL evidence rows with `read_only=true`, `is_order_action=false`, `broker_api_called=false`, and `allowed_for_live_execution=false`. The wrapper prepares a launch command but does not start `run_live.sh` automatically.
