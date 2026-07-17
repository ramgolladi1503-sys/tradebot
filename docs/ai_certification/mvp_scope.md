# TradeBot AI QA and Certification Agent MVP

## Mission

Given an existing strict option-replay WFA output directory, export a frozen evidence bundle, let an AI client inspect and validate targeted evidence through governed MCP tools, and produce a deterministic certification verdict that fails closed when proof is incomplete.

## Included

- Additive exporter for existing `OptionBacktestEngine` and option-replay WFA artifacts
- Byte-for-byte preservation of raw WFA reports and partition journals
- Independent dataset file hash and source-provenance index
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
- Optional read-only MCP tools for inspection, individual gates, retrieval, and final certification
- Versioned MCP policy resource

## Excluded

- Live trade decisions
- Broker or order APIs
- Risk-gate changes
- Strategy generation or optimization
- Production feed certification
- PR review and code mutation
- Arbitrary filesystem, shell, database, or Git access
- Automatic merge or deployment

## Architecture boundary

The certification core is additive under `core.ai_certification` and remains independent of the live TradeBot pipeline. The exporter is an explicit adapter that reads files already written by the strict option-backtest and WFA paths; those producers are not changed. The package does not modify the orchestrator, strategy registry, feed pipeline, ranking, risk, execution, broker, option-backtest engine, or WFA implementation.
