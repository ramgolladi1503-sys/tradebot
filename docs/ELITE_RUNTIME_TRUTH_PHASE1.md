# Elite Runtime Truth Phase 1

Branch: `hardening/elite-runtime-truth-roadmap`

This note tracks the first implementation slice for the roadmap.

## Objective

Create one final status authority and stop later layers from raising a candidate above the status already assigned by the core decision layer.

## First files to inspect

```text
core/review_queue.py
core/candidate_finalization.py
core/orchestrator.py
dashboard/ui/table_model.py
strategies/trade_builder.py
```

## First test group

```bash
pytest -q tests/test_review_queue_decision_engine.py tests/test_review_queue_fallback_execution.py tests/test_advisory_level_reconciliation.py
```

## Done condition

- weak candidates stay non-live-actionable
- low rank candidates stay non-live-actionable
- fallback candidates stay advisory/debug only
- final status cannot be raised outside the core decision layer
