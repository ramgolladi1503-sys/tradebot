# Architecture

```mermaid
flowchart TD
    U[Research objective] --> M[LangGraph Research Manager]
    M --> P{Evidence mode}
    P -->|Structural dataset| D[Dataset validator]
    P -->|Legacy report| L[Legacy evidence auditor]
    D --> H[Human approval interrupt]
    L --> H
    H --> T[Temporal semantics tests]
    T --> B[Actual trend_pullback callable replay]
    B --> W[Structural WFA adapter]
    W --> C[Independent adversarial critic]
    L --> C
    C --> J[Deterministic certification judge]
    J --> R[Immutable evidence bundle]
    R --> Y[Bounded hypothesis proposer]
    Y --> G[Duplicate-resistant hypothesis registry]

    X[SQLite checkpointer] --- M
    E[Idempotent execution ledger] --- D
    E --- L
    E --- T
    E --- B
    E --- W
    E --- C
    S[Prompt-injection sanitizer] --- M
    S --- C
```

## Authority separation

| Component | May reason | May calculate metrics | May mutate production | May certify |
| --- | --- | --- | --- | --- |
| Research Manager | Yes | No | No | No |
| Independent Critic | Yes | No | No | No |
| TradeBot tools | No | Yes | No | No |
| Deterministic Judge | Rule evaluation only | Uses tool outputs | No | Yes |
| Human reviewer | Approve/reject plan | No | No through this system | No override of judge |

## Sidecar boundary

Every implementation file lives under `agentic_research/`. The sidecar imports selected deterministic TradeBot research callables but exposes no reverse dependency into the production runtime.
