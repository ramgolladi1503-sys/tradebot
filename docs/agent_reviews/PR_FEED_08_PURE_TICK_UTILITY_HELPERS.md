# Agent Review — PR-FEED-08 Pure Tick Utility Helpers

## Review result

PASS for narrow helper extraction.

## What changed

- Added pure tick utility helpers for epoch coercion, tick timestamp extraction, first-level price extraction, depth bid/ask validation, and deterministic freshness epoch normalization.
- Added focused unit tests for valid and invalid timestamp/price/depth/freshness scenarios.
- Added documentation for scope and exclusions.

## Safety checks

- No broker imports.
- No order behavior.
- No runtime wiring.
- No dashboard/UI work.
- No filesystem writes.
- No hidden clock calls inside the helper module.

## Known limitation

`core/kite_depth_ws.py` is not rewired in this PR. That is intentional: changing a 4k-line live feed file through a full-file connector overwrite is not acceptable without a safe patch path. Future feed refactor PRs can consume this helper module once a controlled diff is available.

## Test command

```bash
python -m pytest tests/test_pr_feed_08_tick_utils.py -q
```
