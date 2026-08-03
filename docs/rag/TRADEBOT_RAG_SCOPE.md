# TradeBot Evidence RAG — Production Scope V1

## Objective

Provide a local, read-only question-answering surface over TradeBot repository evidence. The system must retrieve relevant source text, return line-addressable citations, refuse unsupported questions, and remain isolated from all trading and broker execution paths.

## Included in V1

- Sources: `README.md`, `docs/`, and `research/`.
- Formats: Markdown, text, JSON, YAML.
- Incremental SHA-256 indexing into `.runtime/rag/tradebot_rag.sqlite`.
- Deterministic chunking with source path and line ranges.
- SQLite FTS5 retrieval with a deterministic fallback when FTS5 is unavailable.
- Exact-identifier boosts for PR numbers, commit fragments, strategy IDs, and error codes.
- Extractive answer synthesis. Every answer point carries a `path:Lx-Ly` citation.
- Explicit insufficient-evidence refusal.
- Standalone CLI, standalone Streamlit UI, and deterministic retrieval evaluation.

## Explicitly excluded

- Broker APIs, order routing, trade approval, risk mutation, and strategy mutation.
- Live market recommendations or profitability claims.
- Web crawling and external document ingestion.
- Multi-agent orchestration, knowledge graphs, autonomous repair, and self-modifying prompts.
- Runtime secrets, `.env` files, logs, model binaries, market datasets, and files outside the repository.
- Generative model calls in V1. The default answerer is extractive to keep unsupported claims impossible by construction.

These exclusions are scope controls, not missing architecture. A generative model should be added only after retrieval evaluation is stable and only behind the same citation and refusal contract.

## Commands

Build or refresh the index:

```bash
PYTHONPATH=. python scripts/tradebot_rag.py build
```

Query it:

```bash
PYTHONPATH=. python scripts/tradebot_rag.py query "Why was the ORB hypothesis rejected?"
```

Inspect status:

```bash
PYTHONPATH=. python scripts/tradebot_rag.py status
```

Run retrieval evaluation:

```bash
PYTHONPATH=. python scripts/tradebot_rag.py evaluate
```

Run the UI:

```bash
streamlit run dashboard/tradebot_rag_app.py
```

## Production acceptance gates

1. Unit tests cover source allowlisting, line-addressable chunking, incremental updates, deletion cleanup, retrieval, citations, and unsupported-question refusal.
2. `rag/eval_cases.json` reaches `hit@5 >= 0.80`.
3. Index artifacts remain under ignored `.runtime/` paths.
4. No imported or called code path reaches broker, strategy execution, risk mutation, or live market feeds.
5. Every non-refusal answer contains at least one source citation.
6. Rebuilding an unchanged corpus does not rewrite unchanged documents.

## Iteration rule

Do not add embeddings, rerankers, agents, or an LLM merely because they are fashionable. Add one only when a failed evaluation case proves the current retrieval or synthesis method cannot meet a documented requirement. Every iteration must include a new failing case first, then the smallest fix, then regression validation.
