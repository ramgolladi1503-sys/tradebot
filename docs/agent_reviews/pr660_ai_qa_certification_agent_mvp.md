# PR 660 — AI QA Certification Agent MVP

## Agent Work Contract

Implement a read-only backtest evidence certification module as an additive package. The certification layer may consume frozen evidence and generate reports, but it must not import, mutate, or bypass TradeBot's live feed, strategy, ranking, risk, execution, broker, or order-control paths.

Primary agent ownership:
- `core/ai_certification/**`
- `scripts/run_ai_backtest_certification.py`
- `tests/ai_certification/**`
- `docs/ai_certification/**`
- `requirements-ai-certification.txt`

## Scope Guard

The diff is additive. It contains no modification to existing TradeBot production files, main dependencies, strategy formulas, feed behavior, ranking authority, risk controls, execution behavior, or broker integration.

The optional MCP adapter exposes only bundle inspection, deterministic certification, policy retrieval, and report generation under configured allowlisted roots.

## Grill Me Review

Questions applied:

1. Can an LLM or MCP client override a certification verdict?
   - No. Deterministic validators and the versioned policy own the evidence status and strategy-verdict combinations.
2. Can the new package place or modify a trade?
   - No broker, order, risk-override, strategy-mutation, shell, database-mutation, or Git-write capability exists.
3. Can a bundle escape its configured filesystem root?
   - Relative-path and resolved-root checks reject absolute paths and traversal. Unsafe artifact paths also produce a deterministic rejection report rather than an uncaught exception.
4. Can a valid negative strategy result be represented without being mislabeled as a failed experiment?
   - Yes. Evidence certification and strategy outcome are separate fields.
5. Does missing evidence silently pass?
   - No. Mandatory missing evidence returns `INSUFFICIENT_EVIDENCE`; contradictory evidence returns `REJECTED`.

## Hermes Review

Contract and authority review:

- Source authority is pinned to `core.option_backtest.engine.OptionBacktestEngine` and `core.option_backtest.wfa.run_option_replay_wfa` in `REAL_EXECUTABLE_RESEARCH` mode.
- Legacy, vectorized, proxy, synthetic-liquidity, and hardcoded-metric paths are explicitly non-certifying.
- Artifact hashes, repository commit, policy version, dataset provenance, timing, fills, reconciliation, WFA integrity, controls, and tests are represented as typed gate results.
- The curated knowledge layer is explanatory only and cannot change gate outcomes.

## GSD Review

Implementation completeness for this PR:

- Immutable bundle loader implemented.
- Versioned policy implemented.
- Eleven deterministic gate evaluations implemented.
- Separate evidence and strategy verdicts implemented.
- Deterministic trace and bundle digest implemented.
- JSON and Markdown reports implemented.
- Curated authority-ranked policy retrieval implemented.
- Optional FastMCP server and CLI implemented.
- Focused certification and path-boundary tests implemented.

## QA / Safety Review

Focused checks cover:

- Valid methodology with `NO_STRUCTURAL_EDGE` remains `CERTIFIED`.
- Artifact mutation is rejected as invalid data.
- Same-event entry is rejected as leakage.
- Proxy engine evidence is non-certifying.
- Missing mandatory evidence fails closed.
- Insufficient trades remain distinct from invalid evidence.
- Prompt-injection text embedded in an evidence field is treated as inert data.
- MCP bundle and report paths cannot escape allowlisted roots.
- Unsafe manifest artifact paths produce a rejection report without reading outside the bundle.
- Repeated certification produces identical trace and bundle digests.

The exact isolated suite passed with `10 passed`, and the new package plus CLI passed bytecode compilation.

## Acceptance Proof

- Base commit: `58881fd873c307df3adaa5402ed27936573a1873`
- Branch: `feature/ai-qa-certification-agent-mvp`
- Diff against main: 16 added files, 0 modified existing files, 0 deleted files.
- Local isolated command: `python -m pytest -q tests/ai_certification`
- Result: `10 passed`
- Compilation command: `python -m compileall -q core/ai_certification scripts/run_ai_backtest_certification.py`
- Result: passed
- Main `requirements.txt`: unchanged
- Existing TradeBot production modules: unchanged

## Runtime Proof Required After Merge

Post-merge proof must use an exported evidence bundle from an actual strict `OptionBacktestEngine` plus option-replay WFA run. It must demonstrate at least:

1. A methodologically valid negative result producing `CERTIFIED` plus `NO_STRUCTURAL_EDGE`.
2. A temporally contaminated bundle producing `REJECTED` plus `INVALID_DUE_TO_LEAKAGE`.
3. An incomplete strict-option bundle producing `INSUFFICIENT_EVIDENCE` plus `WITHHELD`.
4. MCP Inspector access restricted to the configured evidence and report roots.

## What This PR Does Not Prove

- It does not prove a strategy has structural edge.
- It does not yet export evidence directly from production option-backtest and WFA objects.
- It does not certify live feed production readiness.
- It does not provide a production-hosted MCP deployment.
- It does not provide a large golden evaluation corpus or provider/model comparison.
- It does not modify or validate live order execution.

## Human Approval

This is a draft PR. Human approval is required before it is marked ready or merged. The intended review decision is whether the additive certification boundary, evidence schema, deterministic gate ownership, and MCP filesystem restrictions are acceptable for the next exporter-integration phase.
