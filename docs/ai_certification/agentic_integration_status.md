# Agentic certification integration status

## Authoritative implementation

This integration extends the `core.ai_certification` package already merged to `main` by PR 660. It does not introduce the older divergent `agentic_research/` tree.

## Priority closure

1. **Original purpose restored:** certification orchestration is the product; strategy studies remain separate evidence inputs.
2. **Clean current-main branch:** `feature/agentic-research-integration-v1` is based directly on current `main`.
3. **Current TradeBot contracts:** the manager calls the merged bundle inspection, targeted gates and deterministic certifier.
4. **CI gates:** focused certification tests, compilation, deterministic evaluation and a read-only AST boundary run in a dedicated workflow; normal repository workflows run on the PR.
5. **Gemini measurement:** a structured manager/critic evaluation runs only through `secrets.GEMINI_API_KEY`; absence is recorded as unmeasured.
6. **Upstox adapter:** directory and ZIP sources are hashed and classified into claim-specific evidence lanes.
7. **Single PR:** the branch targets `main` with an additive diff only.

## Merge rule

Do not merge until all repository workflows are green. A successful dedicated workflow does not override a failed standard test, CI, security or agent-review gate.
