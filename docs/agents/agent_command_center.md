# Tradebot Agent Command Center

This command center is a deterministic, read-only forensic layer for Tradebot.

It does not:

- place or modify orders
- call broker APIs
- change strategy logic
- change ranking/scoring behavior
- change Phase2 behavior
- restart websockets
- mutate live runtime state

## Purpose

The command center inspects existing runtime logs, snapshots, fixtures, and evidence files to explain where the live pipeline breaks:

1. Auth/session
2. Kite REST readiness
3. WebSocket feed
4. Token resolution and subscription
5. Option tick/depth freshness
6. Market data snapshot
7. Indicator/regime readiness
8. TradeBuilder candidate generation
9. Candidate classification
10. Phase2 admission and filtering
11. Ranking and executable emit
12. Review queue
13. Outcome truth and edge measurement

## Agents

- Live RCA Agent
- Feed Stability Agent
- Candidate Supply Agent
- Phase2 / Ranking Truth Agent
- Edge Measurement Agent
- Safety / Regression Gate Agent

## Output Contract

- JSON summary
- Markdown summary
- one latest JSON artifact per agent

## Safety

All outputs must remain read-only:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `no_order_action=true`

## Rollout

The implementation is intentionally phased:

1. shared contracts, readers, and CLI shell
2. per-agent analysis modules
3. validation and command-center summary polish

