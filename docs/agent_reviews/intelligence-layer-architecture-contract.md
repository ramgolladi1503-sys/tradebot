# Agent Review — Intelligence Layer Architecture Contract

## Agent Work Contract

Create documentation-only architecture contracts for the Tradebot Intelligence Layer.

The work defines a future read-only analysis layer that will inspect Tradebot runtime evidence, feed health, candidate flow, ranking quality, strategy edge evidence, and safety boundaries. This PR does not implement runtime behavior.

## Scope Guard

Allowed files:

- `docs/intelligence/INTELLIGENCE_LAYER_BIBLE.md`
- `docs/intelligence/ARCHITECTURE.md`
- `docs/intelligence/SAFETY_BOUNDARIES.md`
- `docs/intelligence/AGENT_CONTRACTS.md`
- `docs/intelligence/ROADMAP.md`
- `docs/agent_reviews/intelligence-layer-architecture-contract.md`

Forbidden scope:

- no broker calls
- no live orders
- no runtime mutation
- no feed restart
- no lock-file mutation
- no strategy changes
- no candidate-generation changes
- no ranking changes
- no risk changes
- no UI changes
- no scripts
- no agents

## Grill Me Review

- Does this place orders? No.
- Does this call broker APIs? No.
- Does this change runtime behavior? No.
- Does this change feed, strategy, candidate flow, ranking, or risk? No.
- Does this create agents or scripts? No.
- Does this weaken tests or CI gates? No.
- Does this document missing-evidence behavior? Yes: missing evidence must produce `unknown` or `insufficient evidence`.

## Hermes Review

This PR documents the Hermes-style direction without implementing agent autonomy.

The architecture explicitly keeps the Intelligence Layer beside Tradebot, not inside the trading path. Future agents are limited to read-only diagnosis, root-cause classification, recommendations, issue drafts, cross-session memory, and edge-improvement decisions.

## GSD Review

The practical value of this PR is scope control. It prevents the next 19 PRs from turning into random AI-agent sprawl.

The documentation locks the build order: evidence registry, evidence loader, and evidence validator must come before diagnostic agents. This is necessary because agents reading files inconsistently would recreate the same truth-fragmentation problem the layer is supposed to fix.

## QA / Safety Review

This PR is documentation-only and should not affect runtime behavior.

Safety boundaries are explicitly documented:

- read-only first
- no broker calls
- no order placement
- no runtime mutation
- no feed restarts
- no threshold changes
- no automatic code changes
- no automatic trading decisions

Future validation must prove these boundaries with tests when code is introduced.

## Acceptance Proof

Required checks before merge:

- `git diff --check main...HEAD`
- Agent review evidence gate must pass.
- Markdown lint may be run if repository tooling exists.

Expected changed files are documentation files only.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR because it does not change runtime code.

Post-merge proof is limited to confirming the documentation exists on `main` and that no runtime modules were changed.

## What This PR Does Not Prove

This PR does not prove:

- feed tradability
- candidate quality
- ranking quality
- strategy edge
- fallback handling correctness
- paper/live readiness
- profitability
- runtime safety implementation
- Intelligence Layer executable behavior

It only proves the architecture contract and roadmap have been documented.

## Human Approval

Human approval is required before merge.

Do not start PR 2 until this PR is merged and the architecture contract is accepted.
