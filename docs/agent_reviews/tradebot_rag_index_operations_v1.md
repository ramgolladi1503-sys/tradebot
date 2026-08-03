# Agent Review — TradeBot RAG Index Operations V1.1

mode: PAPER
candidate_id: TRADEBOT_RAG_INDEX_OPERATIONS_V1_1
decision: APPROVED_FOR_CI_VALIDATION
reason: Adds fail-closed local index build locking and read-only integrity diagnostics without changing retrieval or trading behavior.
timestamp: 2026-08-03T18:05:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/tradebot_rag_index_operations_v1.md

## Purpose

Protect the merged TradeBot Evidence RAG from concurrent supported builds and make index corruption or FTS drift explicitly diagnosable.

## Scope

In scope: one operational module, CLI wiring, Streamlit build wiring, on-demand integrity UI, focused negative tests, RAG CI doctor evidence, scope documentation, and this review record.

Out of scope: retrieval changes, embeddings, reranking, generative answers, new sources, automatic repair, broker calls, strategy logic, risk logic, execution paths, approval paths, and live-market behavior.

## Grill Me Review

### What assumption could silently break this change?

The primary assumption is that supported builds enter through the CLI or standalone Streamlit page. Direct internal calls to `core.tradebot_rag.build_index` remain available for tests and internal code, but operational entrypoints use `build_index_safely`.

### What behavior is claimed but must be proven?

- A second supported build fails before invoking the existing builder.
- A stale lock is reclaimed.
- An old lock owned by a live process on the same host is not reclaimed.
- Lock cleanup cannot delete a replacement lock.
- Doctor uses SQLite read-only mode and reports failed invariants without repairing them.
- Retrieval evaluation remains unchanged.

### What could fail despite basic tests passing?

- FTS virtual-table joins could behave differently across SQLite builds.
- Repository corpus scale could make integrity checks exceed the CI limit.
- Platform-specific process probing could produce permission errors; those are treated as evidence that the owner may still be alive.

## Hermes Scope Review

The change is additive and limited to RAG operational surfaces. No broker, execution, strategy, candidate, scoring, ranking, risk, or main dashboard modules are imported or modified. Workflow permissions remain `contents: read`.

## Minerva Test Review

Negative tests cover competing builds, stale recovery, live-owner protection, active-lock diagnosis, non-database input, document/chunk inconsistency, and FTS row loss. Existing retrieval and refusal tests remain part of the same CI job.

## GSD Delivery Review

Done means:

- focused RAG and operations tests pass;
- real repository index builds through the locked entrypoint;
- doctor reports healthy on the real index;
- retrieval hit@5 remains at least 0.80;
- refusal accuracy remains 1.00;
- repository policy, security, and deterministic test gates pass.

## Safety Evidence

- live_order_action: false
- broker_order_action: false
- execution boundary changes: none
- trading recommendation changes: none
- automatic repair: none

## Human Review

Human approval is required before merge. Verify the PR remains operational-only, CI produces `doctor_report.json`, all checks are green, and no retrieval or trading scope has entered the patch.
