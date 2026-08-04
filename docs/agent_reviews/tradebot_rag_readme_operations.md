# Agent Review — TradeBot Evidence RAG README Operations

mode: PAPER
candidate_id: TRADEBOT_RAG_README_OPERATIONS
decision: APPROVED_FOR_CI_VALIDATION
reason: Documents how to operate the already-merged local Evidence RAG and accurately states its repository source boundaries without changing runtime behavior.
timestamp: 2026-08-04T03:17:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/tradebot_rag_readme_operations.md

## Agent Work Contract

Make the merged TradeBot Evidence RAG discoverable from the root README. Document how to pull, build, inspect, evaluate, query, and launch it, plus what repository evidence it reads and what it excludes. Documentation must match the existing CLI, Streamlit UI, source allowlist, operational lock, and read-only integrity contracts.

## Scope Guard

In scope:

- `README.md` RAG operation instructions;
- links to the existing RAG scope and operations documents;
- this mandatory review evidence record.

Out of scope:

- RAG indexing, retrieval, scoring, ranking, chunking, answer synthesis, refusal, or UI behavior changes;
- embeddings, vector databases, external ingestion, web crawling, agents, or generative model calls;
- broker, feed, strategy, candidate, risk, approval, execution, reconciliation, or live-runtime changes;
- dependency or workflow changes.

## Grill Me Review

### What assumption could silently break this change?

The README commands assume they are run from the repository root and use `PYTHONPATH=.`. The documentation states this explicitly. It also assumes the existing paths `scripts/tradebot_rag.py` and `dashboard/tradebot_rag_app.py` remain the supported entrypoints.

### What behavior is claimed but must be supported by the repository?

- default sources are `README.md`, `docs/`, and `research/`;
- supported suffixes are `.md`, `.txt`, `.json`, `.yaml`, and `.yml`;
- the index path is `.runtime/rag/tradebot_rag.sqlite`;
- CLI commands are `build`, `query`, `status`, `doctor`, and `evaluate`;
- status and doctor are read-only;
- Streamlit exposes build/refresh, integrity check, source filtering, evidence count, question input, confidence, citations, and retrieved chunks;
- unsupported questions are refused;
- broker and trading paths are not invoked.

These claims were checked against the merged implementation and RAG contract documents.

### What could still confuse an operator?

The standalone RAG Streamlit app is separate from the main TradeBot dashboard. The README identifies the exact RAG app path and states that it does not start live trading components.

## Hermes Review

Scope result: PASS_PENDING_REQUIRED_CI.

The patch is documentation-only except for the repository-required review record. It does not change executable code, dependencies, workflows, permissions, or runtime behavior. The README separates RAG operation from live TradeBot operation and preserves the existing no-profitability-claim boundary.

## GSD Review

Delivery verdict: PASS_PENDING_REQUIRED_CI.

Completion requires:

- only `README.md` and this review record are changed;
- README links resolve to existing files;
- commands and source boundaries match merged code;
- mandatory repository checks pass on the final branch head.

## QA / Safety Review

Documentation checks:

- operation commands use supported CLI syntax;
- Streamlit command points to the standalone RAG app;
- source allowlist and supported formats match `core/tradebot_rag.py`;
- excluded data and runtime boundaries do not overstate implementation behavior;
- lock and doctor recovery guidance matches `docs/rag/TRADEBOT_RAG_OPERATIONS_V1.md`;
- example questions remain repository-evidence questions and do not request live trading recommendations.

Safety boundary:

- live_order_action: false
- broker_order_action: false
- broker_api_called: false
- trading behavior changes: none
- runtime code changes: none

## Acceptance Proof

Review the final diff and run the repository documentation and RAG gates. The README must include:

1. pull/update instructions;
2. default sources and supported formats;
3. explicit exclusions;
4. build, status, doctor, evaluate, Streamlit, and query commands;
5. index location and incremental refresh behavior;
6. UI operating steps;
7. troubleshooting guidance;
8. links to the existing RAG scope and operations contracts.

## Runtime Proof Required After Merge

No new runtime proof is required because this PR changes documentation only. Existing merged RAG runtime evidence remains authoritative. A reader may validate the instructions by running:

```bash
PYTHONPATH=. python scripts/tradebot_rag.py build
PYTHONPATH=. python scripts/tradebot_rag.py status
PYTHONPATH=. python scripts/tradebot_rag.py doctor
PYTHONPATH=. python scripts/tradebot_rag.py evaluate
PYTHONPATH=. python -m streamlit run dashboard/tradebot_rag_app.py
```

## What This PR Does Not Prove

- It does not add or modify a RAG capability.
- It does not make the RAG an LLM application, network service, or multi-user service.
- It does not add external data fetching or live market ingestion.
- It does not prove trading strategy quality, profitability, broker readiness, or execution safety.
- It does not replace the detailed RAG scope or operations documents.

## Human Approval

Human approval is required before merge. Confirm the README instructions are understandable, the source and exclusion boundaries are accurate, and no unrelated documentation or runtime change entered the patch.

## Evidence Contract

- mode: PAPER
- candidate_id: TRADEBOT_RAG_README_OPERATIONS
- decision: PASS_PENDING_REQUIRED_CI
- reason: README operation guidance and source-boundary documentation are complete; final-head repository checks remain authoritative.
- timestamp: 2026-08-04T03:17:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/tradebot_rag_readme_operations.md
