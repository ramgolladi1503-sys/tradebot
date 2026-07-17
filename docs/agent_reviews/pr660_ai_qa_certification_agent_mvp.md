# PR 660 — AI QA Certification Agent MVP

mode: REVIEW
candidate_id: PR-660-AI-QA-CERTIFICATION-MVP
decision: DRAFT_REVIEW_REQUIRED
reason: Additive read-only certification module requires human review before merge.
timestamp: 2026-07-17T21:05:00+05:30
is_order_action: false
broker_api_called: false
source: feature/ai-qa-certification-agent-mvp

## Agent Work Contract

Implement a read-only backtest evidence certification module as an additive package. The certification layer may export and consume frozen evidence and generate reports, but it must not mutate or bypass TradeBot's live feed, strategy, ranking, risk, execution, broker, or order-control paths.

Primary agent ownership:
- `core/ai_certification/**`
- `scripts/export_ai_backtest_certification_bundle.py`
- `scripts/run_ai_backtest_certification.py`
- `tests/ai_certification/**`
- `docs/ai_certification/**`
- `requirements-ai-certification.txt`

## Scope Guard

The diff is additive. It contains no modification to existing TradeBot production files, main dependencies, strategy formulas, feed behavior, ranking authority, risk controls, execution behavior, option-backtest engine behavior, WFA behavior, or broker integration.

The exporter reads files already written by the strict option-backtest and WFA paths and preserves the source artifacts byte-for-byte. The optional MCP adapter exposes only bundle inspection, targeted deterministic gates, curated policy retrieval, final certification, and report generation under configured allowlisted roots.

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
5. Does absent mandatory evidence silently pass?
   - No. Mandatory absent evidence returns `INSUFFICIENT_EVIDENCE`; contradictory evidence returns `REJECTED`.
6. Can generated summaries detach from the raw WFA evidence?
   - No. The bundle requires a source index, raw source-file hashes, and a matching physical dataset file hash.

## Hermes Review

Contract and authority review:

- Source authority is pinned to `core.option_backtest.engine.OptionBacktestEngine` and `core.option_backtest.wfa.run_option_replay_wfa` in `REAL_EXECUTABLE_RESEARCH` mode.
- Legacy, vectorized, proxy, synthetic-liquidity, and hardcoded-metric paths are explicitly non-certifying.
- Artifact hashes, source provenance, repository commit, policy version, dataset provenance, timing, fills, reconciliation, WFA integrity, controls, and tests are represented as typed gate results.
- The curated knowledge layer is explanatory only and cannot change gate outcomes.
- The exporter remains an explicit adapter and is not imported by the certification package root.

## GSD Review

Implementation completeness for this PR:

- Immutable bundle loader implemented.
- Real WFA artifact exporter implemented.
- Raw source artifact index implemented.
- Versioned policy implemented.
- Twelve deterministic gate evaluations implemented.
- Separate evidence and strategy verdicts implemented.
- Deterministic trace and bundle digest implemented.
- JSON and Markdown reports implemented.
- Curated authority-ranked policy retrieval implemented.
- Optional FastMCP server with targeted tools implemented.
- Export and certification CLIs implemented.
- Focused certification, exporter, retrieval, and path-boundary tests implemented.

## QA / Safety Review

Focused checks cover:

- Valid methodology with `NO_STRUCTURAL_EDGE` remains `CERTIFIED`.
- Artifact mutation is rejected as invalid data.
- Source dataset identity mismatch is rejected.
- Same-event entry is rejected as leakage.
- Proxy engine evidence is non-certifying.
- Absent mandatory evidence fails closed.
- Insufficient trades remain distinct from invalid evidence.
- Prompt-injection text embedded in an evidence field is treated as inert data.
- MCP bundle and report paths cannot escape allowlisted roots.
- Unknown or action-like MCP gate names are rejected.
- Curated retrieval does not index `.env` or arbitrary repository files.
- Unsafe manifest artifact paths produce a rejection report without reading outside the bundle.
- Repeated certification produces identical trace and bundle digests.
- Existing WFA and partition files are copied byte-for-byte into the frozen bundle.

The branch contains 14 focused tests under `tests/ai_certification`. The earlier certification-core slice passed locally with `10 passed`; the complete current branch is governed by the PR CI checks before merge.

## Acceptance Proof

- Base commit: `58881fd873c307df3adaa5402ed27936573a1873`
- Branch: `feature/ai-qa-certification-agent-mvp`
- Diff against main: 20 added files, 0 modified existing files, 0 deleted files.
- Focused suite command: `python -m pytest -q tests/ai_certification`
- Compilation command: `python -m compileall -q core/ai_certification scripts/export_ai_backtest_certification_bundle.py scripts/run_ai_backtest_certification.py`
- Code Excellence, Agent Review Evidence, Repo Forensics, Portfolio CI, CodeQL, unit-test, CI, and strategy-registry workflows must pass on the final head before merge.
- Main `requirements.txt`: unchanged
- Existing TradeBot production modules: unchanged

## Runtime Proof Required After Merge

Post-merge proof must use an exported evidence bundle from an actual strict `OptionBacktestEngine` plus option-replay WFA run. It must demonstrate at least:

1. A methodologically valid negative result producing `CERTIFIED` plus `NO_STRUCTURAL_EDGE`.
2. A temporally contaminated bundle producing `REJECTED` plus `INVALID_DUE_TO_LEAKAGE`.
3. An incomplete strict-option bundle producing `INSUFFICIENT_EVIDENCE` plus `WITHHELD`.
4. An AI MCP client selecting targeted inspection, retrieval, and validation tools before requesting final certification.
5. MCP access restricted to the configured evidence and report roots.

## What This PR Does Not Prove

- It does not prove a strategy has structural edge.
- It does not certify live feed production readiness.
- It does not provide a production-hosted MCP deployment.
- It does not provide a large golden evaluation corpus or provider/model comparison.
- It does not modify or validate live order execution.

## Human Approval

This is a draft PR. Human approval is required before it is marked ready or merged. The review decision is whether the additive exporter, certification boundary, evidence schema, deterministic gate ownership, curated retrieval, and MCP filesystem restrictions are acceptable for runtime proof.
