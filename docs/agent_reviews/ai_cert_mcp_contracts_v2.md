# AI Certification MCP Contracts v2 Review

mode: REVIEW
candidate_id: AI-CERT-MCP-CONTRACTS-V2
decision: DRAFT_REVIEW_REQUIRED
reason: Versioned MCP contracts and runtime schema enforcement require repository review before integration.
timestamp: 2026-07-18T00:29:19+05:30
is_order_action: false
broker_api_called: false
source: feature/ai-cert-mcp-contracts-v2

## Agent Work Contract

Introduce a versioned and deterministic MCP tool-contract layer around the merged AI certification kernel. The work may strengthen validation and MCP metadata, but it must not modify TradeBot feed, strategy, ranking, risk, execution, broker, option-backtest or WFA behavior.

Owned paths:

- `core/ai_certification/mcp/**`
- `core/ai_certification/mcp_server.py`
- `tests/ai_certification/mcp/**`
- `docs/ai_certification/mcp/**`
- this review evidence

## Scope Guard

The certification engine and deterministic validators remain authoritative. The MCP contract layer validates requests and structured results, publishes a versioned manifest and supplies explicit safety annotations.

The server exposes no live trading, arbitrary filesystem, shell, database mutation, code mutation or Git-write capability. The only write-capable tool persists deterministic certification reports under the existing configured report root.

## Contract Review

The candidate defines:

- internal contract version `1.0.0`
- MCP protocol target `2025-11-25`
- JSON Schema `2020-12`
- 16 deterministic tool contracts
- lexical tool ordering
- canonical manifest SHA-256
- explicit input and output schemas
- explicit authorization scopes
- explicit timeout and payload ceilings
- closed-world safety annotations
- task support set to `forbidden`

## Safety Review

Expected safety properties:

1. Fifteen tools are read-only, non-destructive, idempotent and closed-world.
2. `certify_backtest_bundle` is the only write-capable tool.
3. The report writer is non-destructive, idempotent and closed-world.
4. No contract name or scope grants broker, order, risk, shell, database or Git authority.
5. A minor version cannot weaken safety annotations or expand scopes, timeout or payload budgets.
6. Unknown tools and schema violations fail closed.
7. Server decorators must exactly match the deterministic registry.
8. Unguarded direct `@mcp.tool` registration is prohibited by regression tests.

## QA Plan

Focused tests cover:

- unique deterministic registry order
- semantic version parsing
- JSON-schema object roots and dialect
- explicit `additionalProperties`
- read-only versus report-write separation
- prohibited capability absence
- manifest and digest determinism
- unknown tool rejection
- additive optional-input compatibility
- new required-input rejection
- removed or changed output rejection
- safety weakening rejection
- scope-change rejection
- timeout expansion rejection
- request field and bound validation
- output enum and required-field validation
- response byte-limit enforcement
- server-to-registry drift detection
- unguarded decorator detection

## Architecture Review

This is an additive certification-platform hardening change. It does not change the algorithmic trading architecture. Existing bundle, policy, validator and report owners remain unchanged.

The current `mcp_server.py` continues to host the adapter, but every registered tool is wrapped by the contract validator and receives annotations from the registry rather than hand-authored metadata.

## Acceptance Proof

Pending CI evidence:

- focused MCP contract tests
- full AI certification tests
- repository fast deterministic suite
- Code Excellence
- Agent Review Evidence
- Repo Forensics
- Portfolio CI
- CodeQL
- Verify Strategy Registry

No merge is permitted while any required check is failing or incomplete.

## Exclusions

This candidate does not claim:

- MCP Inspector conformance
- authenticated Streamable HTTP deployment
- OAuth authorization enforcement
- multi-client load testing
- task-augmented execution
- mature hybrid RAG
- agent orchestration quality
- production hosting readiness

Those are separate maturity phases after this contract boundary is accepted.
