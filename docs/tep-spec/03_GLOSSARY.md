# TEP v1 — Canonical Glossary

Status: DRAFT  
Version: 1.0.0-draft

**Application** — Product/domain system using TEP services and missions; does not bypass service ownership.

**Authority** — Explicit permission to perform a capability at a defined scope and time. Access alone is not authority.

**Blocker** — Condition preventing progress. Must be typed when evidence permits.

**Capability** — Named action contract with owner, prerequisites, authority, validators and evidence requirements.

**Certification** — Governed assertion that a named contract has been satisfied by sufficient evidence. Certification scope must be explicit.

**Driver** — Adapter between TEP and an external system. Contains integration mechanics, not domain/business policy.

**Evidence** — Verifiable artifact supporting a specific claim. Sealed governance evidence is immutable/content-addressed.

**Handler** — Service-side component responsible for progressing/resolving a defined task or blocker class under policy.

**Knowledge** — Provenance-bound facts/findings useful for future decisions. Knowledge does not grant mutation authority.

**Mission** — Versioned declarative top-level executable objective containing tasks/phases, dependencies, constraints, capabilities, evidence requirements and completion criteria.

**Phase** — Optional mission grouping/lifecycle boundary containing related tasks and exit conditions.

**Service** — Platform component owning domain semantics and policy for a bounded capability family.

**State** — Durable authoritative representation of a platform entity's lifecycle. State has one authoritative owner.

**Task** — Bounded executable unit in a mission graph with inputs, dependencies, required capability, execution contract and terminal conditions.

**TBOS** — TEP runtime subsystem responsible for durable mission/task orchestration, scheduling, dispatch, event processing and recovery.

**TEP** — TradeBot Engineering Platform; top-level governed platform described by this specification.

**Validator** — Component that independently determines whether an execution result satisfies its contract. Worker assertion alone is insufficient.

**Worker** — Replaceable execution backend (initially Codex) that performs bounded tasks but owns neither mission state nor authority.

**WAITING** — Non-terminal state where progress depends on an external/time/event condition.

**BLOCKED** — Condition requiring classification; generic BLOCKED is not preferred when a precise reason is knowable.

**TRUE_HUMAN_APPROVAL_REQUIRED** — Irreducible state where policy explicitly requires a human decision/approval.

**LIVE_EVIDENCE_REQUIRED** — State where a contract requires fresh governed live-market evidence unavailable from offline/replay evidence.

**IMPLEMENTATION_VALID** — Implementation satisfies defined engineering tests/contracts; does not imply economic validity.

**HISTORICAL_EDGE_SUPPORTED** — Historical evidence supports a specified economic hypothesis under its stated test contract.

**OUT_OF_SAMPLE_SUPPORTED** — Defined out-of-sample/forward-style validation supports the hypothesis under the frozen selection process.

**EXECUTION_VIABLE** — Evidence supports realistic operational execution after costs, liquidity, fills, latency and capacity constraints.

**PROSPECTIVE_SUPPORTED** — Frozen strategy/hypothesis received qualifying future/prospective evidence.

**STRUCTURAL_EDGE_CERTIFIED** — Highest governed economic certification state; requires all applicable validation/evidence gates. Lower states never imply it.