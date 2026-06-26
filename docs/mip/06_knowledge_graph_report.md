# Agent 6 Report: Knowledge Graph Infrastructure

## Objective
Implement an optional, deterministic Market Entity Graph scaffolding. This graph translates regulatory and market events into localized context networks.

## Implementation Rules
1. **No LLM Hallucination**: The graph (`core/intelligence/knowledge/graph.py`) explicitly forbids adding edges without verifiable evidence. LLMs or fuzzy matchers cannot randomly link nodes.
2. **Typed Static Config**: Baseline canonical relationships (e.g., `RBI -> Banking`, `Banking -> BANKNIFTY`) are statically configured as ground truth.
3. **Inferred Markers**: Any edge formed from a parsed event (e.g., a specific SEBI circular affecting a broker) must have `is_inferred=True` and an `evidence_pointer`. The graph refuses construction if an inferred edge lacks an evidence pointer.
4. **Strict Isolation**: The graph is an analysis overlay. It has **no capability** to influence execution state, nor can it generate `candidate` rows. It exists purely as an advisory context tool.
