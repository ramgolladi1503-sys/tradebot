# Tradebot Intelligence Layer Roadmap

## Roadmap Rules

This roadmap builds the Tradebot Intelligence Layer beside Tradebot, not inside the trading path.

Hard rules:

- Do not start agents before PR 2, PR 3, and PR 4 are complete.
- Do not build a dashboard before backend intelligence proves useful.
- Do not allow the Intelligence Layer to mutate Tradebot runtime.
- Do not add broker calls, order placement, feed restarts, or threshold mutation.
- Every PR must preserve the read-only boundary unless a later roadmap explicitly changes it and adds safety review.
- Every conclusion must be evidence-backed or explicitly marked `unknown` / `insufficient evidence`.

## PR 1 - Intelligence Layer Architecture Contract

### Goal

Create the source-of-truth documentation for the Intelligence Layer.

### Allowed Scope

- Add architecture docs.
- Define safety boundaries.
- Define future agent contracts.
- Define the 20-PR roadmap.

### Forbidden Scope

- No code.
- No scripts.
- No agents.
- No runtime integration.
- No trading behavior changes.

### Acceptance Proof

- Read-only boundary is explicit.
- No-broker/no-order/no-runtime-mutation rule is explicit.
- Evidence-first and unknown-on-missing-evidence rules are explicit.
- Future agents and roadmap are documented.

### Test / Documentation Expectation

- `git diff --check`
- Markdown lint if repo tooling exists.

## PR 2 - Evidence Source Registry

### Goal

Create a deterministic registry of evidence sources that the Intelligence Layer may read.

### Allowed Scope

- Add registry module or data contract.
- Define source names, path patterns, required/optional status, owner agent, and read-only status.
- Add tests for discovery and missing-source behavior.

### Forbidden Scope

- No agents.
- No RCA logic.
- No runtime mutation.
- No broad repo scanning outside registry.

### Acceptance Proof

- Registry can discover latest live-session evidence.
- Registry clearly reports missing required evidence.

### Test / Documentation Expectation

- Unit tests for registry loading and source discovery.
- Docs or comments for registry fields.

## PR 3 - Session Evidence Loader

### Goal

Load one market session into a normalized evidence object.

### Allowed Scope

- Add session evidence model.
- Add loader that reads registered sources.
- Preserve raw source references and missing source list.

### Forbidden Scope

- No diagnosis.
- No agent conclusions.
- No trading behavior changes.

### Acceptance Proof

- Complete session loads into normalized evidence.
- Missing files are recorded, not hidden.

### Test / Documentation Expectation

- Unit tests with complete and incomplete fixture sessions.

## PR 4 - Evidence Quality Validator

### Goal

Validate whether loaded evidence is trustworthy enough for agents.

### Allowed Scope

- Validate required fields, timestamps, session consistency, stale files, impossible values, and schema drift.
- Return structured validation status.

### Forbidden Scope

- No agent-specific diagnosis.
- No RCA prioritization.
- No runtime mutation.

### Acceptance Proof

- Rejects session/date mismatch.
- Rejects impossible values such as negative quote age marked healthy.

### Test / Documentation Expectation

- Unit tests for valid, missing, stale, contradictory, and impossible evidence.

## PR 5 - Feed Doctor Agent

### Goal

Diagnose feed tradability, not just websocket connection.

### Allowed Scope

- Implement Feed Doctor against validated session evidence.
- Classify websocket, index tick, option tick, quote freshness, subscription health, and reconnect effectiveness.

### Forbidden Scope

- No feed restart.
- No broker call.
- No subscription mutation.

### Acceptance Proof

- Connected websocket with stale option quotes is marked not tradable.
- Reconnect without restored freshness is marked ineffective.

### Test / Documentation Expectation

- Unit tests for connected-but-not-tradable, fresh index/stale option, recovery blocked, and insufficient evidence.

## PR 6 - Candidate Flow Agent

### Goal

Identify where candidates die in the pipeline.

### Allowed Scope

- Map counts and blockers across auth, feed, instruments, option selection, indicators, strategy generation, Phase 2, risk, ranking, executable, and approval queue.

### Forbidden Scope

- No strategy changes.
- No threshold changes.
- No candidate promotion.

### Acceptance Proof

- Phase 2 rejection is not blamed on strategy generation.
- Ranking is marked inconclusive when too few candidates reach ranking.

### Test / Documentation Expectation

- Unit tests for each major blocker category and insufficient evidence.

## PR 7 - Ranking Quality Agent

### Goal

Detect whether ranking is decision-useful.

### Allowed Scope

- Detect score compression, missing/defaulted scores, fallback contamination, candidate insufficiency, and display-vs-ranking confusion.

### Forbidden Scope

- No ranking weight changes.
- No threshold changes.
- No UI changes.

### Acceptance Proof

- Narrow confidence band is flagged as compressed.
- Single candidate is marked inconclusive.
- Fallback-driven candidates are flagged as contaminated.

### Test / Documentation Expectation

- Unit tests for compressed, meaningful, defaulted, fallback-contaminated, and insufficient ranking.

## PR 8 - Strategy Edge Agent

### Goal

Classify strategy usefulness by evidence and regime without premature edge claims.

### Allowed Scope

- Analyze strategy evidence with regime, feed quality, candidate flow, and outcome context.

### Forbidden Scope

- No strategy parameter changes.
- No strategy promotion from one session.
- No new strategy logic.

### Acceptance Proof

- Feed degradation blocks strategy-edge conclusion.
- Repeated poor outcomes classify strategy as weak/harmful only when sample requirements are met.

### Test / Documentation Expectation

- Unit tests for insufficient data, feed contamination, promising, weak, harmful, and regime-dependent classifications.

## PR 9 - Risk and Safety Boundary Agent

### Goal

Verify live/audit/manual-approval/fail-closed safety boundaries.

### Allowed Scope

- Analyze safety evidence and mode flags.
- Detect broker order path touch in audit-only mode.

### Forbidden Scope

- No order placement.
- No risk-control mutation.
- No approval mutation.

### Acceptance Proof

- Order path touch in audit-only is critical violation.
- Recovery blocked with stopped runtime is marked correct fail-closed behavior.

### Test / Documentation Expectation

- Unit tests for safe, unsafe, critical violation, unknown, and insufficient evidence.

## PR 10 - Evidence Integrity Agent

### Goal

Detect contradictions, stale files, schema drift, and fake healthy states.

### Allowed Scope

- Compare registered evidence sources.
- Block or downgrade weak conclusions when integrity is poor.

### Forbidden Scope

- No evidence rewriting.
- No silent contradiction suppression.

### Acceptance Proof

- Contradictory feed/quote evidence is flagged.
- Missing evidence prevents fake RCA.

### Test / Documentation Expectation

- Unit tests for contradiction, schema drift, stale evidence, fake healthy state, and trustworthy evidence.

## PR 11 - Agent Orchestrator

### Goal

Run diagnostic agents against a session and collect structured results.

### Allowed Scope

- Deterministic orchestration.
- Skip or downgrade agents when evidence quality fails.

### Forbidden Scope

- No runtime mutation.
- No report styling beyond minimal structured output.

### Acceptance Proof

- Runs all diagnostic agents.
- Evidence quality failure blocks or downgrades affected agents.

### Test / Documentation Expectation

- Unit tests for full run, partial run, validation failure, and deterministic ordering.

## PR 12 - Root Cause Prioritization Engine

### Goal

Rank many findings into a dominant root-cause list.

### Allowed Scope

- Implement priority order: safety, feed, evidence integrity, candidate flow, ranking, strategy edge.

### Forbidden Scope

- No issue generation.
- No strategy tuning.

### Acceptance Proof

- Safety violation outranks all other issues.
- Feed tradability issue deprioritizes strategy-edge conclusions.

### Test / Documentation Expectation

- Unit tests for priority ordering and blocked downstream conclusions.

## PR 13 - Daily Session RCA Report Generator

### Goal

Generate Markdown and JSON RCA reports for one session.

### Allowed Scope

- Write reports under `.runtime/intelligence/reports/`.
- Include summary, evidence quality, agent findings, dominant RCA, what not to change, and next action.

### Forbidden Scope

- No dashboard.
- No issue creation.

### Acceptance Proof

- Report says do not tune strategy when feed is unusable.
- Report says ranking inconclusive when candidate count is too low.

### Test / Documentation Expectation

- Snapshot or golden-file tests for report content.

## PR 14 - Improvement Recommendation Engine

### Goal

Convert RCA into scoped engineering recommendations.

### Allowed Scope

- Produce title, priority, reason, evidence refs, allowed scope, forbidden scope, and suggested tests.

### Forbidden Scope

- No code changes from recommendations.
- No automatic PRs.

### Acceptance Proof

- Feed issue creates feed-scoped recommendation only.
- Ranking issue forbids strategy changes.

### Test / Documentation Expectation

- Unit tests for feed, candidate, ranking, safety, and evidence-integrity recommendations.

## PR 15 - GitHub Issue Draft Exporter

### Goal

Generate paste-ready issue drafts from recommendations.

### Allowed Scope

- Write Markdown drafts under `.runtime/intelligence/github_issue_drafts/`.

### Forbidden Scope

- No GitHub API calls.
- No auto-created issues.
- No auto-created PRs.

### Acceptance Proof

- Draft includes problem, evidence, scope, forbidden changes, acceptance criteria, and tests.
- Safety-sensitive drafts include no-broker/no-live-order boundary.

### Test / Documentation Expectation

- Golden-file tests for draft output.

## PR 16 - Post-Market Intelligence Runner

### Goal

Add one command to run the Intelligence Layer after market.

### Allowed Scope

- Add CLI runner for latest or specified session.
- Run loader, validator, agents, orchestrator, RCA, recommendations, reports, and drafts.

### Forbidden Scope

- No live runtime mutation.
- No dashboard.
- No broker calls.

### Acceptance Proof

- Latest session run creates report and issue drafts.
- Missing session fails clearly.

### Test / Documentation Expectation

- CLI tests for success, missing session, and validation failure.

## PR 17 - Market-Day Watch Mode

### Goal

Observe live evidence files during market without touching runtime.

### Allowed Scope

- Read evidence files repeatedly.
- Emit read-only intelligence snapshots and warnings.

### Forbidden Scope

- No feed restart.
- No runtime mutation.
- No threshold changes.
- No broker calls.

### Acceptance Proof

- Detects connected-but-not-tradable feed during market.
- Emits warning without mutating bot state.

### Test / Documentation Expectation

- Tests using temporary files and deterministic polling hooks.

## PR 18 - Intelligence Memory Store

### Goal

Track repeated patterns across sessions.

### Allowed Scope

- Store session finding summaries and pattern counts under `.runtime/intelligence/memory/`.
- Escalate repeated issues based on count and recency.

### Forbidden Scope

- No strategy promotion without minimum samples.
- No live behavior mutation.

### Acceptance Proof

- Repeated feed issue escalates after multiple sessions.
- Strategy edge remains insufficient until sample threshold is met.

### Test / Documentation Expectation

- Unit tests for pattern accumulation, escalation, and insufficient-sample behavior.

## PR 19 - Strategy Expectancy Intelligence

### Goal

Measure strategy usefulness across regimes using clean evidence.

### Allowed Scope

- Compute candidate count, qualified count, executable count, paper/sim outcome count, win rate, average R, MAE, MFE, regime context, and feed-quality context.

### Forbidden Scope

- No live orders.
- No strategy changes.
- No broker adapter work.

### Acceptance Proof

- Strategy is not judged when feed quality is degraded.
- Strategy is classified by regime, not globally praised or killed.

### Test / Documentation Expectation

- Unit tests for clean evidence, contaminated evidence, insufficient samples, and regime-specific classification.

## PR 20 - Edge Improvement Decision Board

### Goal

Produce one final daily edge-improvement decision.

### Allowed Scope

- Decide among fix feed, fix candidate flow, fix ranking, collect more data, promote strategy, suspend strategy, or do nothing.

### Forbidden Scope

- No trade execution.
- No automatic code changes.
- No automatic PRs.
- No strategy/risk/ranking mutation.

### Acceptance Proof

- Upstream feed break blocks strategy tuning.
- Healthy feed/pipeline with no edge recommends strategy review or data collection.

### Test / Documentation Expectation

- Unit tests for each decision class and blocked-decision explanation.
