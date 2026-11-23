# Work Item: EPIC-APM-WAL-DURABILITY-001

## Identity

- Work Item ID: `EPIC-APM-WAL-DURABILITY-001`
- Type: `EPIC`
- Parent Epic: none
- Parent Feature: none
- Title: Active Position Manager WAL durability and ownership
- Current State: `BACKLOG`
- Priority: `HIGH`

## Business Goal

Keep Active Position Manager recovery state protected from concurrent ownership, path aliasing, and process interruption. This Epic concerns persistence integrity only; it does not establish trading performance or live readiness.

## Scope boundary

Includes APM WAL ownership identity, atomic persistence and recovery evidence. Excludes strategy rules, thresholds, broker/order behavior, credentials, live configuration, deployment and market-performance claims.

## Safety constraints

- `read_only=true` for verification work.
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- Fail closed when lock ownership or filesystem guarantees are unknown.
