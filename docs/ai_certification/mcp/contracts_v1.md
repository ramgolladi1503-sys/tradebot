# TradeBot AI Certification MCP Contract v1

## Contract identity

- Internal contract version: `1.0.0`
- Target MCP protocol revision: `2025-11-25`
- Manifest resource: `tradebot://certification/mcp/contracts/v1`
- Manifest digest: deterministic SHA-256 over the ordered tool contracts
- JSON Schema dialect: `2020-12`

The internal contract version is independent from the MCP protocol revision. A protocol upgrade does not silently change the TradeBot tool contract, and an internal additive contract release does not claim a new MCP protocol revision.

## Authority boundary

The MCP server exposes certification capabilities only. It does not expose broker, order, strategy mutation, risk override, shell, database mutation or Git-write operations.

The deterministic certification engine remains authoritative. MCP metadata, an LLM client and retrieved policy text cannot override a gate result or final evidence status.

## Tool classes

### Closed-world read-only tools

The following operations are read-only, non-destructive, idempotent and closed-world:

- bundle inspection
- deterministic individual gates
- policy retrieval
- deterministic policy inspection

They require one of:

- `certification:inspect`
- `certification:evaluate`
- `certification:retrieve`

### Report writer

`certify_backtest_bundle` is the only tool allowed to modify its environment. Its write is restricted to deterministic JSON and Markdown reports under the configured report root.

It is:

- not read-only
- non-destructive
- idempotent for the same immutable bundle and policy
- closed-world
- protected by `certification:report:write`

It cannot modify the evidence bundle or any TradeBot runtime component.

## Required contract fields

Every tool contract declares:

- stable programmatic name
- human-readable title and description
- semantic contract version
- input JSON Schema
- output JSON Schema
- safety annotations
- task-support policy
- timeout
- request and response byte limits
- required authorization scopes

All input and output schemas use an object root and explicitly state `additionalProperties`.

## Runtime enforcement

Before a tool implementation executes, the wrapper validates:

1. required input fields
2. unknown input fields
3. types, enums, patterns and bounds
4. canonical JSON serialization
5. request byte limit

Before a result is returned, it validates:

1. required output fields
2. structured result types
3. unknown output fields where prohibited
4. finite numeric values
5. response byte limit

Validation failures are fail-closed and do not return a nominally successful tool result.

## Registration integrity

The server may register a tool only through the contract-aware `registered_tool` wrapper. Static regression tests compare every decorator name with the deterministic registry and reject unguarded `@mcp.tool` registrations.

## Task execution

All v1 tools declare task support as `forbidden`. Long-running task augmentation, polling and resumable task state are outside this contract and require a future explicit contract release.
