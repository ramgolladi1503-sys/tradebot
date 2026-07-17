# MCP Certification Contract Compatibility Policy

## Versioning

TradeBot MCP tool contracts use `MAJOR.MINOR.PATCH` semantic versions.

- **Patch:** implementation or documentation correction with identical observable contract.
- **Minor:** backward-compatible additive contract change.
- **Major:** any breaking input, output, scope, safety or execution change.

## Minor-release rules

A minor release may:

- add an optional input property
- add an output property while preserving all existing output properties
- strengthen descriptions without changing behavior
- reduce timeout or payload ceilings
- strengthen a safety guarantee

A minor release may not:

- remove or change an existing input property
- introduce a new required input
- remove or change an existing output property
- make a previously required output optional
- change required authorization scopes
- change task-support behavior
- expand timeout or payload budgets
- weaken read-only, non-destructive, idempotent or closed-world guarantees

## Major-release triggers

A major release is required to:

- rename or remove a tool
- change the meaning of an existing field
- add a required argument
- change result shape incompatibly
- permit new side effects
- expose open-world access
- alter authorization scopes
- enable task-augmented execution
- expand the filesystem or service boundary

## Registry and digest

Tool ordering is lexical and deterministic. The manifest digest is calculated from canonical JSON over the complete ordered registry.

Any contract change changes the digest. A client may pin the digest for strict compatibility or pin the semantic major version while allowing proven compatible minor releases.

## Fail-closed behavior

Unknown tools, invalid semantic versions, invalid schemas, duplicate names, unsorted or duplicate scopes and incompatible minor releases raise contract errors during import or test execution.

Runtime request or result schema violations raise `MCPContractValidationError`. They must not be converted into successful certification responses.

## Release evidence

Every contract release must provide:

1. registry uniqueness and deterministic-order proof
2. schema-root and JSON-dialect proof
3. safety-annotation proof
4. prohibited-capability proof
5. compatibility positive and negative controls
6. server-to-registry drift proof
7. focused and repository-wide test results
8. agent review evidence

MCP Inspector and transport conformance are separate follow-on gates. Passing this contract release does not claim authenticated HTTP deployment or cross-client production readiness.
