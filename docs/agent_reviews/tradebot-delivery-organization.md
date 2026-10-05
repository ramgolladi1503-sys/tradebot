# Agent Review Evidence — TradeBot Permanent Delivery Organization

## Agent Work Contract

- source_agent: ChatGPT / repository governance implementation
- action: DEFINE_CONTRACT + UPDATE_DOCS
- title: Permanent TradeBot Delivery Organization
- scope: repository governance and delivery workflow only
- requested_paths: docs/tradebot_delivery/*, .agents/rules/*, .agents/workflows/*, AGENTS.md, .github templates
- forbidden_paths: runtime trading code, broker, execution, risk, strategies, credentials
- expected_tests: docs/static consistency and CI only
- acceptance_proof: organization, lifecycle, roles, QA loop, and release gates are repository-owned and referenced by agent instructions

## Scope Guard

This change must not alter runtime, broker, strategy, feed, execution, risk, or live behavior.

## Grill Me Review

Primary failure risks:
- governance exists only as prose and is never referenced by agent entrypoints;
- role separation conflicts with existing Hermes -> GSD flow;
- templates omit acceptance/QA/release evidence;
- future agents bypass the new lifecycle.

Mitigation:
- wire the organization into AGENTS.md and repository templates;
- explicitly preserve Hermes -> GSD inside the broader workflow;
- require explicit states and evidence.

## Hermes Review

Architecture decision:
- extend existing agent-control structure;
- do not replace current safety controls;
- make TradeBot delivery organization repository-native;
- separate product/architecture/development/QA/release responsibilities;
- preserve fail-closed workflow states.

## GSD Review

Implementation is documentation/governance only. No runtime patch is required.

## QA / Safety Review

Required checks:
- no runtime-sensitive paths changed;
- no broker/risk/execution files changed;
- no safety rule weakened;
- existing Hermes -> GSD rule preserved;
- PR and issue templates reference the new workflow.

## Acceptance Proof

Pass when:
- permanent organization documentation exists;
- delivery lifecycle and blocking states are explicit;
- adversarial QA loop is mandatory;
- role self-approval is forbidden;
- Release Manager cannot merge with failed required gates;
- agent orchestrator is the default workflow entrypoint;
- AGENTS.md references the permanent model.

## Runtime Proof Required After Merge

None. Documentation/governance only.

## What This PR Does Not Prove

- It does not prove Sentinel correctness.
- It does not implement market replay.
- It does not certify a trading edge.
- It does not change order execution or broker behavior.

## Human Approval

Owner approval required before merge.
