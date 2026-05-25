# PR-FEED-20 — Feed Runtime Evidence Bundle

## Purpose

PR-FEED-20 adds a read-only feed runtime evidence bundle contract.

The previous feed PRs created canonical feed truth, feed hold behavior, mode-specific policy, and config hardening. This PR packages those facts into one deterministic evidence object that runtime wiring can emit later.

## Scope

In scope:

- Add `core/feed_runtime_evidence.py`.
- Build `FeedRuntimeEvidenceBundle`.
- Include feed policy decision payload.
- Include feed policy config audit payload.
- Include sanitized runtime feed snapshot.
- Include normalized symbols, mode, reasons, feed status, and metadata.
- Include explicit non-action fields:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

Out of scope:

- No runtime file writing.
- No dashboard wiring.
- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No ranking changes.
- No strategy changes.
- No broker calls.
- No order behavior.

## Bundle contents

`build_feed_runtime_evidence_bundle(...)` returns `FeedRuntimeEvidenceBundle` with:

- `schema_version`
- `mode`
- `feed_ok`
- `reason_code`
- `reasons`
- `symbols`
- `feed_policy_decision`
- `feed_policy_config_audit`
- `runtime_feed_snapshot`
- `metadata`

## Snapshot sanitization

The snapshot copies only known feed-health keys:

- `feed_ok`
- `effective_ws_connected`
- `ws_connected`
- `runtime_state`
- `last_tick_age_sec`
- `last_depth_age_sec`
- option/symbol feed-health maps
- selected `state_machine` fields

Unknown top-level keys are not copied into evidence. Their names are captured in `snapshot_keys` for diagnostic visibility.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_20_feed_runtime_evidence_bundle.py tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Required proof:

- Bundle is read-only and non-action.
- Bundle embeds policy decision and config audit payloads.
- Bundle sanitizes runtime feed snapshot.
- Invalid runtime payload fails closed.
- Invalid config fails closed.
- JSON payload includes `is_order_action=false` and `broker_api_called=false`.
- SIM/BACKTEST mode uses SIM policy.

## Runtime Proof Required After Merge

Later runtime wiring must prove:

- Bundle is emitted once per scoped runtime cycle.
- LIVE/PAPER/SIM policy is visible in evidence.
- Invalid payload/config cannot emit healthy evidence.
- Evidence remains read-only and broker-free.
- No order action path consumes this bundle as permission to trade.

## Risk

Low. This PR creates an evidence contract only. It does not write files, call runtime systems, connect websockets, call brokers, or affect ranking/strategy execution.

## Next PR

After this PR is merged and CI is green, continue only to the next roadmap item after PR-FEED-20.
