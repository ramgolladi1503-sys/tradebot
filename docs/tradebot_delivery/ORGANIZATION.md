# TradeBot Permanent Delivery Organization

## Product model

TradeBot is the product. All repository work is organized as:

```text
Product -> Epic -> Feature -> Story / Bug / Task
```

No implementation task may bypass product analysis, architecture review, QA, acceptance, and release gates.

## Permanent logical roles

### Product Owner
Owns product intent, prioritization, acceptance criteria, and final product acceptance.

### Business Analyst
Converts user intent into testable requirements, identifies dependencies and exclusions, and maintains requirement traceability.

### Solution Architect
Owns cross-system design, reuse of existing TradeBot infrastructure, integration boundaries, and prevention of duplicate architecture.

### System Architect
Owns interfaces, data flow, concurrency, state ownership, runtime lifecycle, and technical invariants.

### Quant / Research Architect
Owns research-method correctness, empirical-contract review, leakage prevention, calibration boundaries, and separation of engineering success from research claims.

### Backend Developer
Implements Python/runtime behavior and unit/integration tests.

### Data / Quant Developer
Implements historical-data, analytics, calibration, feature, and replay components.

### Integration Developer
Owns event adapters, broker/feed integration boundaries, canonical interfaces, and live/replay parity plumbing.

### UI Developer
Owns UI work only when explicitly in scope. Backend stories must not create UI work by default.

### QA Engineer
Owns functional, regression, negative, boundary, and contract testing.

### Senior QA / Adversarial QA
Actively attacks the implementation, files defects, retests fixes, and continues adversarial testing until satisfied.

### UAT Reviewer
Validates business behavior and acceptance criteria. Backend-only work may use contract-based UAT.

### Release Manager
Owns PR readiness, CI, versioning, release notes, release gates, and rollback instructions.

### Production / SRE Owner
Owns deployment verification, runtime health, monitoring, smoke checks, and production verification.

## Separation of duties

No role may approve its own work.

Examples:

- Developer cannot declare `QA_PASSED`.
- QA cannot declare `PRODUCT_ACCEPTED`.
- Product Owner cannot bypass `CI_FAILED`.
- Release Manager cannot merge around required QA/UAT failures.
- Architecture authors may not self-certify implementation correctness.

Logical roles may be executed by AI agents or one human in sequence, but evidence must preserve role separation.

## Permanent rule

All future TradeBot work enters through the TradeBot Delivery Orchestrator defined in:

`.agents/workflows/tradebot-delivery-orchestrator.md`

This organization extends, rather than replaces, the existing Hermes -> GSD agent safety pipeline.
