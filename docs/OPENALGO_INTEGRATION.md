# OpenAlgo Integration (feature/openalgo-integration)

This branch integrates OpenAlgo as an execution backend without modifying the existing main execution path.

## What was added
- `core/brokers/openalgo_client.py` – REST client for OpenAlgo V1 endpoints
- `core/brokers/openalgo_execution_router.py` – router that uses OpenAlgo in LIVE mode
- `main_openalgo.py` – alternate entrypoint wiring the OpenAlgo router

## How to run

1. Install and run OpenAlgo locally or on a server
2. Export env variables:

```
export OPENALGO_ENABLED=true
export OPENALGO_HOST=http://127.0.0.1:5000
export OPENALGO_API_KEY=your_api_key
```

3. Run bot with OpenAlgo execution:

```
python main_openalgo.py
```

## Notes
- SIM/PAPER modes are unchanged
- LIVE mode routes orders through OpenAlgo `/api/v1/placeorder`
- No changes were made to existing execution logic in main branch

## Why this design
- Zero risk to existing bot
- Clear separation of execution layer
- Easy rollback by switching entrypoint

## Next steps (you should do)
- Add order status sync using `/orderstatus`
- Add cancel/modify flow
- Add reconciliation between OpenAlgo and tradebot DB
- Add sandbox mode validation pipeline
