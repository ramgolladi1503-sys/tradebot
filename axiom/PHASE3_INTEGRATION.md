# Phase 3 – Axiom UI Integration

## What was added

- FastAPI backend: `axiom/api/server.py`
- REST endpoints:
  - /api/home
  - /api/top-opportunities
  - /api/advisory
  - /api/review-queue
  - /api/system-health
- WebSocket stream: /ws/home

## How to run

```bash
uvicorn axiom.api.server:app --reload --port 8000
```

## What changed conceptually

Before:
- UI consumed raw rows
- No separation of executable vs advisory

Now:
- UI consumes structured payloads from `ui_api_contract`
- Only real executable trades are marked as executable

## Next required steps

1. Remove REST_FALLBACK from executable logic in Streamlit
2. Replace any websocket raw rendering with `/api/home`
3. Delete duplicate `core_bot` inside axiom repo

## Outcome

- Clean UI contract
- No fake trades
- Ready for ranking engine phase
