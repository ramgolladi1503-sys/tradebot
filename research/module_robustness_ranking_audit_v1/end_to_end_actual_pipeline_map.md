# End-to-End Actual Pipeline Map

Mapped current lifecycle:

```text
main.py/runtime startup -> broker/auth/feed websocket modules -> tick/quote/depth/option-chain state -> market/regime features -> strategies/strategy_registry.py and strategies/movement/* -> strategies/trade_builder.py -> Phase 1/Phase 2 aliases including core/_engine_phase2_adapter_base.py -> candidate pool/normalization/classification/downgrade -> risk/executable truth -> core/orchestrator.py and core/ranking_orchestrator.py -> scoring/ranking/ranked snapshots -> dashboard/streamlit_app_runtime.py -> core/approval_store.py/review_queue -> core/orders/order_intent.py -> core/execution/chokepoint.py and core/execution_engine/router.py -> broker acknowledgement/update surfaces -> core/broker_truth_reconciler.py/core/reconciliation.py
```

No live broker API was called. Reconciliation and broker acknowledgement are mapped but not behaviorally certified in this PR.
