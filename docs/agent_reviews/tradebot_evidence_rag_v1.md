# Agent Review — TradeBot Evidence RAG V1

mode: PAPER
decision: APPROVED_FOR_REVIEW_AFTER_CI
reason: Adds a local read-only evidence retrieval surface without broker, strategy, risk, approval, or execution behavior.
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/tradebot_evidence_rag_v1.md

## Agent Work Contract

Build the smallest useful TradeBot RAG: index allowlisted repository evidence, retrieve line-addressable chunks, return extractive citation-first answers, and refuse unsupported questions. The change is limited to a new core module, CLI, standalone Streamlit page, focused tests, evaluation cases, CI, scope documentation, and this review record.

## Scope Guard

In scope: `README.md`, `docs/`, and `research/` text evidence; SHA-256 incremental indexing; SQLite FTS retrieval; deterministic fallback retrieval; citations; refusal; CLI; standalone UI; evaluation and CI.

Out of scope: broker calls, order actions, live recommendations, strategy tuning, scoring changes, risk mutation, execution wiring, external web ingestion, agents, knowledge graphs, and generative model calls.

## Grill Me Review

Challenge: Is this architecture work without a usable product?

Answer: No. The PR supplies executable build, query, status, evaluation, and Streamlit entrypoints. The index is stored under ignored `.runtime/rag/` and can answer directly from the current repository corpus.

Challenge: Can unrelated questions produce confident TradeBot answers?

Answer: Stop words are removed before retrieval, low-support retrieval is refused, and CI includes explicit unrelated-question refusal cases.

Challenge: Can copied local dumps or runtime material enter the corpus?

Answer: Discovery is allowlisted and rejects hidden files, symlinks, excluded runtime/data/log/model directories, imported `external_local_dirs`, known raw process/environment/credential dump stems, oversized files, unsupported suffixes, and paths outside the repository.

## Hermes Review

The public surface is narrow: index build, search, grounded ask, status, and default index path. Outputs are immutable dataclasses. SQL values are parameterized. The system is additive and does not import TradeBot runtime, broker, strategy, execution, or risk modules.

## GSD Review

The smallest useful implementation is deliberately extractive. It avoids embeddings, rerankers, agents, and an LLM until a failed evaluation case demonstrates a concrete need. This prevents architecture drift while providing a complete local evidence-search workflow now.

## QA / Safety Review

Covered negative paths include unsupported questions, outside-repository includes, symlinks, hidden files, imported local evidence directories, raw process dumps, undecodable changed sources, deleted sources, stale FTS rows, and missing index state. Changed-source failures remove prior indexed evidence so stale content does not survive silently.

## Acceptance Proof

Required commands:

```bash
PYTHONPATH=. pytest -q -o addopts='' tests/test_tradebot_rag.py
PYTHONPATH=. python scripts/tradebot_rag.py build
PYTHONPATH=. python scripts/tradebot_rag.py evaluate --min-hit-at-k 0.80 --min-refusal-accuracy 1.00
PYTHONPATH=. python scripts/tradebot_rag.py status
```

Acceptance requires focused tests to pass, real-corpus retrieval hit@5 of at least 0.80, refusal accuracy of 1.00, and citation-bearing output for supported questions.

## Runtime Proof Required After Merge

Run the standalone page with `streamlit run dashboard/tradebot_rag_app.py`, build the index from the merged checkout, ask one supported and one unsupported question, and confirm that no TradeBot broker/runtime process starts and no order-related side effect occurs.

## What This PR Does Not Prove

It does not prove semantic retrieval across paraphrases that share no repository vocabulary. It does not prove answer quality for PDFs or binary artifacts. It does not prove any trading strategy, profitability claim, or live-market decision. It does not make the existing main TradeBot dashboard use RAG.

## Human Approval

Human approval is required before merge. The reviewer must verify the PR remains read-only, all required checks are green, the real-corpus evaluation report meets its thresholds, and no broker, strategy, risk, or execution scope entered the patch.

## High-Risk Path Review

N/A. No configured high-risk runtime path is changed.

## Evidence Contract

- mode: PAPER
- decision: PASS_PENDING_REQUIRED_CI
- reason: Scoped implementation and local proof complete; repository CI is authoritative for merge readiness.
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
