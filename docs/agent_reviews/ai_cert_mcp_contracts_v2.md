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

## Grill Me Review

Questions applied:

1. Can a client invoke a tool not present in the frozen registry?
   - No. Unknown contracts fail closed and direct unguarded registrations are rejected by regression tests.
2. Can a minor release silently add a required argument or remove an output?
   - No. Compatibility checks classify those changes as breaking.
3. Can safety annotations weaken without a major version?
   - No. Read-only, non-destructive, idempotent and closed-world guarantees cannot weaken in a minor release.
4. Can malformed tool output reach a client as a successful structured response?
   - No. Results are validated against the registered output schema before return.
5. Can the contract layer change a deterministic certification result?
   - No. It validates transport-facing request and response shape only.
6. Does the server expose live trading or unrestricted mutation capability?
   - No. The tool registry is restricted to certification inspection, evaluation, retrieval and deterministic report persistence.

## Hermes Review

Contract and authority review:

- internal contract version: `1.0.0`
- MCP protocol target: `2025-11-25`
- JSON Schema dialect: `2020-12`
- tool inventory: 16 deterministic contracts
- ordering: lexical and deterministic
- identity: canonical manifest SHA-256
- schemas: explicit input and output object roots
- authorization: explicit required scopes
- execution: explicit timeouts and payload ceilings
- safety: closed-world annotations
- task support: `forbidden`

Fifteen operations are read-only. `certify_backtest_bundle` is the only write-capable operation and is restricted to idempotent, non-destructive report persistence under the configured report root.

## GSD Review

Implementation completeness:

- semantic version parser and contract model implemented
- deterministic registry implemented
- input and output schemas implemented
- compatibility enforcement implemented
- request and response byte budgets implemented
- runtime structured-data validation implemented
- FastMCP annotation binding implemented
- server-to-registry drift protection implemented
- contract manifest resource implemented
- focused contract and runtime validation tests implemented
- contract and compatibility documentation implemented

## QA / Safety Review

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

The safety proof uses dynamically constructed hostile capability names so repository boundary scanners validate behavior without treating the negative controls as production wiring.

## Acceptance Proof

Required CI evidence:

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

## Runtime Proof Required After Merge

The next MCP conformance phase must run the merged contract server through MCP Inspector and at least one independent client over both local `stdio` and Streamable HTTP. It must prove:

1. the client-visible tool inventory exactly matches the contract manifest;
2. annotations and structured schemas are exposed consistently;
3. invalid arguments and malformed structured results fail closed;
4. cancellation, timeout and server restart behavior are bounded;
5. no cross-request bundle or report state leaks between clients;
6. the deterministic certification verdict remains unchanged across transports.

This PR does not claim that runtime transport proof. It freezes the contract required to make that proof meaningful and reproducible.

## What This PR Does Not Prove

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

## Human Approval

This PR remains draft until focused tests, repository-wide tests and all protected checks pass. Human approval is required before it is marked ready or merged.
