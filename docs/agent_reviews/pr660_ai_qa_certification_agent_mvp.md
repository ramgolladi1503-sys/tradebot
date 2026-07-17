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
   - Relative-path, resolved-root, and symlink checks reject traversal. Hostile run IDs are converted to deterministic safe filenames.
4. Can a valid negative strategy result be represented without being mislabeled as a failed experiment?
   - Yes. Evidence certification and strategy outcome are separate fields.
5. Does absent mandatory evidence silently pass?
   - No. Mandatory absent evidence returns `INSUFFICIENT_EVIDENCE`; contradictory evidence returns `REJECTED`.
6. Can generated summaries detach from the raw WFA evidence?
   - No. The certifier cross-checks raw WFA engine identity, run ID, strict mode, frozen configuration hash, action boundary, required source roles, raw controls, raw tests, completed-partition files, source-file hashes, and physical dataset identity.
7. Can one absent artifact downgrade a separate explicit failure?
   - No. `AGENT_ERROR` and `REJECTED` take precedence over `INSUFFICIENT_EVIDENCE`.
8. Can a single repeated holdout use pass because the count is below two?
   - No. Any nonzero `repeated_holdout_run_count` fails the mandatory walk-forward integrity gate.

## Hermes Review

Contract and authority review:

- Source authority is pinned to `core.option_backtest.engine.OptionBacktestEngine` and `core.option_backtest.wfa.run_option_replay_wfa` in `REAL_EXECUTABLE_RESEARCH` mode.
- Legacy, vectorized, proxy, synthetic-liquidity, and hardcoded-metric paths are explicitly non-certifying.
- Artifact hashes, source provenance, repository commit, policy version, dataset provenance, timing, fills, reconciliation, WFA integrity, controls, and tests are represented as typed gate results.
- Required source roles include the WFA report, control input, test input, and summary/journal/decision artifacts for every completed partition.
- Raw controls and test results must reconcile with normalized certification artifacts.
- Repeated holdout use is zero-tolerance: only a count of zero is certifying.
- The curated knowledge layer is explanatory only and cannot change gate outcomes.
- The exporter remains an explicit adapter and is not imported by the certification package root.

## GSD Review

Implementation completeness for this PR:

- Immutable bundle loader implemented.
- Real WFA artifact exporter implemented.
- Raw source artifact index implemented.
- Required source-role completeness implemented.
- Raw-WFA-to-derived-authority cross-check implemented.
- Raw-control and raw-test reconciliation implemented.
- Versioned policy implemented.
- Twelve deterministic gate evaluations implemented.
- Separate evidence and strategy verdicts implemented.
- Deterministic trace and bundle digest implemented.
- Safe deterministic JSON and Markdown report persistence implemented.
- Curated authority-ranked policy retrieval implemented.
- Optional FastMCP server with targeted tools implemented.
- Export and certification CLIs implemented.
- Shared exporter-shaped QA fixture implemented.
- Formal QA test plan and traceability matrix implemented.

## QA / Safety Review

The branch contains **45 automated QA test functions** covering functional behavior, happy paths, positive paths, negative paths, fail-closed precedence, integration, ad-hoc misuse, source consistency, report persistence, and filesystem boundaries.

Focused checks include:

- Valid methodology with `NO_STRUCTURAL_EDGE` remains `CERTIFIED`.
- Valid supported edge maps to `STRUCTURAL_EDGE_SUPPORTED`.
- Insufficient trades remain distinct from invalid evidence.
- Artifact mutation is rejected as invalid data.
- Source dataset identity mismatch is rejected.
- Raw WFA engine, mode, run ID, configuration hash, and action boundary must match generated evidence.
- Required control, test, and completed-partition source roles cannot be omitted.
- Raw controls and normalized controls must match.
- Raw test totals and commit identity must match normalized test evidence.
- Same-event entry is rejected as leakage.
- Proxy engine evidence is non-certifying.
- Absent mandatory evidence fails closed.
- Explicit failure is not downgraded by a simultaneous absent artifact.
- Fallback liquidity and proxy execution evidence are rejected.
- Financial reconciliation, any repeated holdout use, control, and test failures block certification.
- Validator exceptions return `AGENT_ERROR`.
- Prompt-injection text embedded in evidence remains inert data.
- MCP bundle and report paths cannot escape allowlisted roots.
- Curated retrieval does not index `.env` or arbitrary repository files.
- Unsafe manifest paths and symlink escapes are rejected.
- Repeated certification produces identical trace IDs and bundle digests.
- Existing WFA and partition files are copied byte-for-byte into the frozen bundle.
- Exporter refuses to overwrite a nonempty output directory.

## QA-Discovered Defects Fixed

1. **Failure precedence defect**
   - Previous behavior: an `UNEVALUATED` gate could mask a separate mandatory `FAIL`.
   - Fixed behavior: `AGENT_ERROR` > `REJECTED` > `INSUFFICIENT_EVIDENCE` > `CERTIFIED`.
2. **Hostile report-name defect**
   - Previous behavior: a run ID containing no safe filename characters raised an exception after certification.
   - Fixed behavior: deterministic trace-based fallback filename, with a 96-character bound.
3. **Raw/derived authority detachment defect**
   - Previous behavior: generated engine identity was not cross-checked against the frozen raw WFA report.
   - Fixed behavior: engine, run ID, strict mode, config hash, read-only flag, and action boundary must agree.
4. **Incomplete source-index semantics**
   - Previous behavior: listed files were hash-checked, but required control, test, and completed-partition roles were not mandatory and normalized controls/tests were not reconciled.
   - Fixed behavior: required roles are enforced and raw control/test evidence must match normalized artifacts.
5. **Invalid happy-path fixture defect**
   - Previous test data declared one repeated holdout run while expecting certification.
   - Fixed test data declares zero repeated holdout runs.
6. **Repeated-holdout threshold defect**
   - Previous behavior: `repeated_holdout_run_count=1` passed because rejection was incorrectly limited to counts greater than one.
   - Fixed behavior: every nonzero repeated-holdout count returns `REJECTED` with `REPEATED_HOLDOUT_USE`.

## Acceptance Proof

- Base commit: `58881fd873c307df3adaa5402ed27936573a1873`
- Branch: `feature/ai-qa-certification-agent-mvp`
- Diff against main before temporary diagnostics cleanup: 26 intended additive files plus one temporary diagnostics workflow.
- Focused suite command: `python -m pytest -q tests/ai_certification`
- Focused result after repeated-holdout fix: **45 passed** on commit `f53fd32543cdf90fd5a07b07dacbf7b47ed96de1`.
- Focused test inventory: 45 tests.
- Compilation command: `python -m compileall -q core/ai_certification scripts/export_ai_backtest_certification_bundle.py scripts/run_ai_backtest_certification.py`
- Code Excellence, Agent Review Evidence, Repo Forensics, Portfolio CI, CodeQL, unit-test, CI, and strategy-registry workflows must pass on the final cleanup head before merge.
- Main `requirements.txt`: unchanged.
- Existing TradeBot production modules: unchanged.

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
- It does not provide cryptographic signing of the manifest.
- It does not modify or validate live order execution.

## Human Approval

This is a draft PR. Human approval is required before it is marked ready or merged. The review decision is whether the additive exporter, certification boundary, evidence schema, deterministic gate ownership, curated retrieval, QA coverage, and MCP filesystem restrictions are acceptable for runtime proof.
