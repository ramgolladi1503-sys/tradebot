# AI Certification Agent Evaluation v1 Review

mode: REVIEW
candidate_id: AI-CERT-AGENT-EVAL-V1
decision: DRAFT_REVIEW_REQUIRED
reason: Provider-independent golden cases and safety thresholds require review before an agent runner is implemented.
timestamp: 2026-07-18T00:52:00+05:30
is_order_action: false
broker_api_called: false
source: test/ai-cert-agent-evals-v2-main

## Agent Work Contract

Define the first immutable evaluation contract for the TradeBot AI certification agent. This lane owns only evaluation schemas, golden-case data, tests and documentation. It must not modify certification production code, MCP implementation, TradeBot runtime modules or shared deterministic gate contracts.

Owned paths:

- `tests/ai_certification/evals/**`
- `docs/ai_certification/evaluation/**`
- this review evidence

## Scope Guard

The candidate introduces no model calls and executes no agent workflow. It validates the structure and safety expectations of an initial 40-case benchmark.

The deterministic certification engine remains the final verdict authority. The benchmark evaluates future orchestration behavior without granting live trading, risk override, shell, database, code mutation or Git-write capabilities.

## Grill Me Review

Questions applied:

1. Does the matrix falsely claim model performance?
   - No. It is explicitly described as a schema and taxonomy foundation with no executed model result.
2. Can a case require an unknown or unsafe tool?
   - No. Required tools are allowlisted and every case must preserve the complete prohibited-tool guard.
3. Can a prompt-injection case omit adversarial text?
   - No. The loader rejects prompt-injection cases without non-empty untrusted text.
4. Can an abstention case still claim a strategy result?
   - No. Every abstention must use `WITHHELD`.
5. Can a case create an unbounded tool loop?
   - No. Tool budgets are mandatory and limited to twelve calls.
6. Does this branch alter MCP or certification production contracts?
   - No. Its file ownership is restricted to evaluation tests and documents.

## Hermes Review

Evaluation contract:

- schema version: `1.0`
- case IDs: stable `AGENT-CATEGORY-NNN` form
- initial inventory: 40 cases
- categories: happy path, missing evidence, invalid evidence, conflicting evidence, tool failure, prompt injection, wrong-tool temptation and loop control
- verdict dimensions: evidence certification and strategy verdict
- orchestration dimensions: required tools, prohibited tools, abstention and maximum calls
- zero-tolerance targets: false certification and unsafe tool calls

The benchmark is provider-independent and does not embed one model vendor or one agent framework into the case contract.

## GSD Review

Implementation completeness:

- evaluation dataclasses implemented
- fail-closed matrix loader implemented
- allowed category and verdict vocabularies implemented
- allowed certification-tool inventory implemented
- prohibited capability guard implemented
- 40-case golden matrix implemented
- category distribution tests implemented
- unique-ID tests implemented
- tool expectation tests implemented
- abstention tests implemented
- prompt-injection tests implemented
- tool-failure budget tests implemented
- malformed matrix negative controls implemented
- evaluation methodology documented

## QA / Safety Review

Automated checks verify:

- exact 40-case inventory and declared category counts
- unique deterministic identifiers
- required tools remain inside the certification allowlist
- prohibited capabilities are present in every effective case guard
- required and forbidden tool sets never overlap
- tool budgets remain between one and twelve
- abstention always withholds strategy claims
- prompt-injection cases include untrusted text
- wrong-tool temptation cases abstain without invoking unsafe capabilities
- tool-failure cases include fault injection and bounded retry budgets
- invalid category, unknown tool, incomplete guard and duplicate-ID inputs are rejected

The current matrix is not an executable model benchmark yet. Fixture realization and an agent runner are deliberately separate phases.

## Acceptance Proof

Required evidence before merge:

- focused evaluation schema tests
- repository fast deterministic suite
- Code Excellence
- Agent Review Evidence
- Repo Forensics
- Portfolio CI
- CodeQL
- Verify Strategy Registry

No performance claim or agent-quality score may be published from this PR.

## Runtime Proof Required After Merge

The next phase must map every fixture identifier to an immutable bundle or deterministic mutation and implement a provider-neutral runner that records:

1. ordered tool calls;
2. tool arguments after redaction;
3. final evidence status and strategy verdict;
4. abstention behavior;
5. unsafe-call attempts;
6. tool-call count, retries, latency, token usage and cost;
7. trace and case-manifest identity.

The runner must prove zero false certifications and zero unsafe tool calls before any deployment-readiness claim.

## What This PR Does Not Prove

This candidate does not prove:

- that an LLM selects tools correctly;
- that any model reaches the expected verdict;
- that citations are accurate;
- that tool failure recovery works in a live runtime;
- that the 40 cases satisfy the final 150-case target;
- that real TradeBot WFA bundles have been evaluated;
- that the system is production ready.

## Human Approval

This PR remains draft until repository checks pass and the case taxonomy, safety thresholds and explicit non-claims are reviewed. Human approval is required before merge.
