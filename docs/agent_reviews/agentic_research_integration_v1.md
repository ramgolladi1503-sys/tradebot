# Agentic Research Integration v1

mode: REVIEW
candidate_id: AGENTIC-RESEARCH-INTEGRATION-V1
decision: DRAFT_REVIEW_REQUIRED
reason: Extend the merged read-only certification authority with durable orchestration, secure model evaluation, and Upstox evidence classification.
timestamp: 2026-07-18T00:45:00+05:30
is_order_action: false
broker_api_called: false
source: feature/agentic-research-integration-v1

## Agent Work Contract

Extend the existing `core.ai_certification` package from current `main`. Preserve deterministic certification authority and add only read-only research orchestration, model-quality measurement, and dataset eligibility classification.

Primary ownership:

- `core/ai_certification/research_manager.py`
- `core/ai_certification/gemini_client.py`
- `core/ai_certification/evaluation.py`
- `core/ai_certification/upstox_corpus.py`
- `scripts/run_ai_certification_research_manager.py`
- `scripts/run_ai_certification_evaluation.py`
- `scripts/build_upstox_certification_manifest.py`
- `tests/ai_certification/test_research_manager_v1.py`
- `tests/ai_certification/test_agent_evaluation_v1.py`
- `tests/ai_certification/test_upstox_corpus_adapter.py`
- `.github/workflows/agentic-research-integration.yml`

## Scope Guard

The branch is based directly on current `main`. It does not modify orchestrator, feed, strategies, ranking, risk, execution, broker, `OptionBacktestEngine`, option-replay WFA, or the root dependency file.

The existing deterministic certification policy, validators and final verdict ownership remain unchanged. Gemini can only suggest a next action that exactly matches the deterministic state transition. The Upstox adapter creates hashes and eligibility metadata but never copies, rewrites or deletes raw data.

## Grill Me Review

1. Can Gemini override the final verdict?
   - No. Existing deterministic certification remains final authority.
2. Can Gemini skip approval or targeted gates?
   - No. The manager accepts a model action only when it exactly equals the deterministic expected action.
3. Can the manager place an order or modify production state?
   - No broker, order, risk override, shell, code mutation or Git-write capability exists.
4. Can a restart repeat expensive certification actions?
   - The SQLite idempotency ledger reuses prior outputs by deterministic action fingerprint.
5. Can the API key be written into prompts or artifacts?
   - Secret-bearing fields are recursively redacted. The key is sent only as an HTTP header and evaluation artifacts contain no key.
6. Can zero-volume Upstox candles be promoted to VWAP evidence?
   - No. They are classified `PRICE_STRUCTURE_ONLY`.
7. Can positive volume without futures identity be treated as futures evidence?
   - No. It is quarantined as `POSITIVE_VOLUME_IDENTITY_UNCONFIRMED`.
8. Can ZIP traversal write outside a destination?
   - The adapter never extracts members and explicitly rejects absolute or parent-traversal names.

## Hermes Review

- The merged `core.ai_certification` package remains authoritative.
- Model output is advisory and constrained by the deterministic planner.
- Human approval is a state transition, not prompt text.
- SQLite writes are limited to the sidecar state database and report output root.
- Bundle access remains restricted by existing allowlisted-root resolution.
- Upstox evidence classification is conservative and claim-specific.
- The model-quality gate measures manager accuracy, stability, critic blocker recall, unsafe recommendations, exceptions and numeric fabrication.
- An absent repository secret produces an explicit unmeasured artifact, not a fake model score.

## GSD Review

Implemented:

- durable research-run state;
- human approval pause and resume;
- deterministic action ordering;
- optional Gemini planner with strict fallback;
- idempotent action ledger;
- deterministic critic;
- structured Gemini REST client;
- recursive secret redaction;
- deterministic and online evaluation harnesses;
- directory and ZIP Upstox corpus scanning;
- file-level SHA-256 identity;
- futures-volume, price-only and quote-replay evidence lanes;
- dedicated CI workflow;
- focused regression tests and operator documentation.

## QA / Safety Review

Focused coverage proves:

- no evidence tools run before approval;
- a complete approved run certifies and critiques a known-good frozen bundle;
- restart preserves output and avoids duplicate ledger rows;
- out-of-order Gemini actions are ignored;
- step-budget exhaustion fails closed;
- deterministic routing is fully correct;
- secrets are removed recursively;
- Gemini structured requests do not place payload secrets in the request body;
- a controlled online-evaluation oracle meets all quality thresholds;
- positive-volume futures data is eligible;
- zero-volume index data remains price-structure-only;
- quote rows are only replay candidates;
- ZIP traversal is rejected;
- positive volume without futures identity is not promoted.

## High-Risk Path Review

No live high-risk path is modified.

- feed: unchanged
- strategy formulas: unchanged
- candidate ranking: unchanged
- risk gates: unchanged
- broker and order APIs: unchanged
- option replay engine: unchanged
- WFA implementation: unchanged
- production database schemas: unchanged

The only persistent state added is the optional sidecar SQLite research ledger under a user-selected path.

## Acceptance Proof

Required before merge:

- `PYTHONPATH=. pytest -q -o addopts='' tests/ai_certification`
- `python -m compileall -q core/ai_certification`
- deterministic evaluation report with 100% routing accuracy and zero unsafe actions;
- dedicated read-only AST boundary gate;
- full repository `tests` and `ci` workflows green;
- Agent Review Evidence Gate green;
- CodeQL and repository policy checks green;
- direct diff against current `main` contains only the declared sidecar, tests, docs, scripts and workflow files.

## Runtime Proof Required After Merge

1. Build an Upstox corpus manifest from the user's actual replay directory or ZIP.
2. Select only evidence eligible for the intended claim.
3. Export one real strict `OptionBacktestEngine` plus WFA bundle.
4. Run the research manager through approval, targeted gates, deterministic certification and critique.
5. Add a rotated `GEMINI_API_KEY` repository secret and publish the online evaluation artifact.

## What This PR Does Not Prove

- It does not prove profitable edge.
- It does not certify zero-volume candles for VWAP.
- It does not certify option execution merely from quote-shaped columns.
- It does not grant live-trading authority.
- It does not claim Gemini quality when the secure evaluation has not run.

## Human Approval

The PR must remain draft until current-main CI is green and the exact diff boundary is reviewed. No automatic merge is authorized.
