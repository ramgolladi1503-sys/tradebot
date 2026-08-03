# Agent Review — TradeBot RAG Index Operations V1.1

mode: PAPER
candidate_id: TRADEBOT_RAG_INDEX_OPERATIONS_V1_1
decision: APPROVED_FOR_CI_VALIDATION
reason: Adds fail-closed local index build locking plus non-mutating status and integrity diagnostics without changing retrieval or trading behavior.
timestamp: 2026-08-03T18:05:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/tradebot_rag_index_operations_v1.md

## Agent Work Contract

Protect the merged TradeBot Evidence RAG from concurrent supported builds and make SQLite, metadata, document/chunk, lock, foreign-key, and FTS inconsistencies explicitly diagnosable. Operational status and doctor inspection must be read-only. Existing retrieval, refusal, corpus allowlists, and trading boundaries must remain unchanged.

## Scope Guard

In scope:

- one additive RAG operations module;
- CLI safe-build, read-only status, and doctor wiring;
- standalone Streamlit safe-build and on-demand integrity wiring;
- focused lock, corruption, and non-mutation regressions;
- RAG CI doctor evidence;
- operational scope documentation and this review record.

Out of scope:

- retrieval scoring, ranking, answer synthesis, embeddings, rerankers, vector databases, agents, or generative answers;
- new corpus sources or file formats;
- automatic database repair from status or doctor;
- broker calls, strategy logic, candidate logic, risk logic, execution paths, approval paths, and live-market behavior;
- unrelated cleanup or refactoring.

Files not to touch include TradeBot broker, strategy, candidate, ranking, risk, execution, approval, and main runtime modules.

## Grill Me Review

### What assumption could silently break this change?

Supported production builds must enter through the CLI or standalone Streamlit page. Those entrypoints use `build_index_safely`. Direct internal calls to `core.tradebot_rag.build_index` remain limited to the core implementation and existing tests, so this PR does not claim to intercept arbitrary third-party calls.

### What behavior is claimed but must be proven?

- A competing supported build fails before invoking the existing builder.
- A stale lock is reclaimed only when no live same-host owner is detected.
- Lock cleanup cannot delete a replacement owner’s lock.
- A failed lock metadata write leaves no false build marker.
- Status and doctor use read-only SQLite connections and do not create schema or repair FTS rows.
- Doctor detects declared/actual chunk drift, orphan chunks, FTS row loss, foreign-key violations, schema mismatch, corruption, and active locks.
- Existing retrieval and refusal metrics do not regress.

### What could fail despite basic tests passing?

- SQLite FTS virtual-table behavior could differ between environments.
- Full-corpus integrity joins could exceed the CI limit.
- Process liveness probing could return permission errors; these are conservatively treated as possible live ownership.
- A direct internal builder caller outside the supported entrypoints would not acquire the operational lock.

## Hermes Review

Scope result: PASS_PENDING_REQUIRED_CI.

The change is additive and restricted to RAG operational surfaces. It does not import or modify broker, execution, strategy, candidate, scoring, ranking, risk, approval, or main runtime modules. GitHub workflow permissions remain restricted to `contents: read`. The patch does not introduce order actions, broker calls, background services, or automatic repair.

## GSD Review

Delivery verdict: PASS_PENDING_REQUIRED_CI.

Evidence required for completion:

- focused RAG and operations tests pass;
- the real repository corpus builds through the locked entrypoint;
- read-only doctor reports healthy on the generated index;
- read-only status reports inventory without mutation;
- retrieval hit@5 remains at least 0.80;
- unsupported-question refusal accuracy remains 1.00;
- repository policy, security, deterministic test, and health gates pass.

Next action: retain draft status until every required check passes on the final branch head. No earlier-head green result may substitute for final-head evidence.

## QA / Safety Review

Negative coverage includes:

- competing build refusal;
- stale-lock recovery;
- old lock owned by a live same-host process;
- simulated partial lock metadata write failure;
- active-lock diagnosis;
- missing index without creation;
- unreadable/non-database index;
- document/chunk count inconsistency;
- FTS row loss without repair;
- read-only status inventory without mutation;
- existing retrieval and unsupported-question refusal regressions.

Safety boundary evidence:

- live_order_action: false
- broker_order_action: false
- broker_api_called: false
- execution boundary changes: none
- trading recommendation changes: none
- automatic repair: none

## Acceptance Proof

Required commands:

```bash
PYTHONPATH=. pytest -q -o addopts='' tests/test_tradebot_rag.py tests/test_tradebot_rag_operations.py
PYTHONPATH=. python scripts/tradebot_rag.py build
PYTHONPATH=. python scripts/tradebot_rag.py doctor
PYTHONPATH=. python scripts/tradebot_rag.py status
PYTHONPATH=. python scripts/tradebot_rag.py evaluate --min-hit-at-k 0.80 --min-refusal-accuracy 1.00
```

Acceptance requires all commands to succeed on the real repository corpus, `doctor` to report every configured invariant as passing, status to be readable with no build lock present, retrieval hit@5 of at least 0.80, refusal accuracy of 1.00, and all mandatory repository checks to pass.

## Runtime Proof Required After Merge

From the merged main checkout:

1. Build the repository index through `scripts/tradebot_rag.py build`.
2. Run `scripts/tradebot_rag.py doctor` and verify every check passes.
3. Run `scripts/tradebot_rag.py status` and verify it reports a readable index with no active build lock.
4. Launch `streamlit run dashboard/tradebot_rag_app.py`.
5. Trigger one supported query and one unsupported query.
6. Attempt a second supported build while the first lock is held and confirm it fails with `rag_build_in_progress` without damaging the index.
7. Confirm no broker, strategy, risk, execution, approval, or main TradeBot runtime process is started by these operations.

## What This PR Does Not Prove

- It does not make the RAG a network service, multi-user service, or distributed lock system.
- It does not prevent direct callers from bypassing the supported safe-build entrypoints.
- It does not provide automatic database repair or backup restoration.
- It does not improve semantic retrieval, add embeddings, or add generative answers.
- It does not prove trading strategy quality, profitability, broker readiness, or live-market safety.
- It does not change the original V1 corpus scope or retrieval contract.

## Human Approval

Human approval is required before merge. Verify the PR remains operational-only, final-head CI produces `doctor_report.json`, all mandatory checks are green, and no retrieval or trading scope has entered the patch.

## Evidence Contract

- mode: PAPER
- candidate_id: TRADEBOT_RAG_INDEX_OPERATIONS_V1_1
- decision: PASS_PENDING_REQUIRED_CI
- reason: Operational lock, read-only inspection, and negative-test implementation are complete; final-head repository CI remains authoritative.
- timestamp: 2026-08-03T18:05:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/tradebot_rag_index_operations_v1.md
