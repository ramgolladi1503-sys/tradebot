# TradeBot AI QA and Certification Agent MVP

## Mission

Given a frozen strict option-replay evidence bundle, independently determine whether the experiment is trustworthy, explain each blocker with evidence references, and fail closed when proof is incomplete.

## Included

- Immutable evidence bundle validation
- Source-authority enforcement
- Dataset provenance checks
- Temporal-causality checks
- Executable-fill checks
- Cost and P&L reconciliation
- Walk-forward integrity checks
- Negative-control and test-evidence checks
- Separate evidence and strategy verdicts
- Deterministic trace identity
- JSON and Markdown reports
- Curated, authority-ranked policy retrieval
- Optional read-only MCP tools and policy resource

## Excluded

- Live trade decisions
- Broker or order APIs
- Risk-gate changes
- Strategy generation or optimization
- Production feed certification
- PR review and code mutation
- Arbitrary filesystem, shell, database, or Git access

## Architecture boundary

The module is additive under `core.ai_certification`. It consumes exported evidence artifacts and does not import or modify the live orchestrator, strategy registry, feed pipeline, ranking, risk, execution, or broker modules.
