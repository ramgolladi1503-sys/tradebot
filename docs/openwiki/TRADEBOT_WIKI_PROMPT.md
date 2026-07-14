Generate and maintain an evidence-first code wiki for TradeBot.

## Core rule

Do not infer that code is active merely because it exists.

Every runtime-relevant component or path must be classified as exactly one of:

- ACTIVE_PRODUCTION
- ACTIVE_CONDITIONAL
- LEGACY_ACTIVE
- LEGACY_INACTIVE
- SHADOW
- RESEARCH_ONLY
- DEPRECATED
- DEAD
- UNKNOWN

Every important conclusion must be classified as one of:

- PROVEN
- PARTIALLY_PROVEN
- CLAIMED
- UNKNOWN

Repository code, startup wiring, configuration defaults, passing tests, bounded runtime traces, and immutable runtime artifacts may support PROVEN claims. Existing documentation and agent handoffs are supporting context, not proof.

## Documentation priorities

Build a concise, navigable repository wiki covering:

1. quickstart and safe local operation
2. executable entry points
3. canonical runtime startup and shutdown
4. market-data ingestion and websocket lifecycle
5. normalization, timestamps, freshness, and canonical feed truth
6. indicator and market-regime computation
7. strategy invocation
8. candidate creation and identity
9. eligibility, filtering, fallback handling, scoring, and ranking
10. trade building
11. risk, governance, kill switches, and manual approval
12. runtime publication, snapshots, dashboard readers, and alerts
13. execution interfaces without invoking any broker action
14. persistence, journals, ledgers, and reconciliation
15. replay, option backtesting, WFA, and strategy-validation boundaries
16. observability, evidence, and operational debugging
17. testing guidance mapped to the paths tests actually exercise
18. legacy, duplicate, shadow, research, and deprecated paths

## Required questions

The wiki must help an engineer answer:

- Where does a live or replay tick enter?
- Which component establishes canonical feed truth?
- Which strategy functions are actually invoked by the configured runtime?
- Where is a candidate created and how is its identity propagated?
- Which scoring and ranking implementation is actually active?
- What exact object, store, or snapshot does each UI surface read?
- Which gates control candidate visibility, approval eligibility, and execution eligibility?
- Which persistence targets record decisions and outcomes?
- Which backtesting path is suitable for certification and which paths are legacy or proxy-only?
- Where does evidence stop and uncertainty begin?

## Duplicate-path discipline

Explicitly call out:

- legacy and newer candidate pipelines that coexist
- multiple ranking implementations
- multiple backtest engines
- alternate UI publication paths
- fallback paths that bypass normal eligibility or ranking
- active code with no tests
- tests that exercise non-production code only
- architecture documents that describe planned rather than implemented behavior

Do not select a canonical path until callers, startup wiring, configuration, and tests support it.

## Safety rules

- Never read or reproduce credentials, tokens, `.env` contents, broker secrets, or private keys.
- Never place, modify, cancel, or exit an order.
- Never call broker APIs.
- Never weaken risk, freshness, kill-switch, approval, or execution gates.
- Never describe offline or replay evidence as live-market proof.
- Never describe ranking infrastructure as strategy edge.
- Never describe a component as production-ready without an explicit valid certification gate.

## Wiki structure

Prefer a small number of substantial pages over one page per file.

The entry page must link to:

- architecture and runtime flow
- market data
- decision and candidate pipeline
- risk, governance, approval, and execution boundaries
- persistence and observability
- replay, backtesting, and WFA
- operations and debugging
- testing and evidence
- legacy and duplicate paths
- source map

Each major page should include:

- purpose
- runtime classification
- upstream and downstream dependencies
- important source paths and symbols
- configuration controlling activation
- data objects passed
- persistence or publication side effects
- failure behavior
- relevant tests
- known contradictions
- remaining UNKNOWN items

## Change guidance

For each major subsystem, document:

- where an engineer should start
- which files are high risk
- which tests are required
- which evidence must be updated
- what must not be inferred from a passing unit test

Keep the wiki concise, cross-linked, and useful to both humans and coding agents.
