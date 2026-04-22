from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.ui_api_contract import (
    get_advisory_payload,
    get_axiom_home_payload,
    get_review_queue_payload,
    get_system_health_payload,
    get_top_opportunities_payload,
)


app = FastAPI(title="Axiom UI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("AXIOM_UI_CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_REFRESH_SEC = max(1.0, float(os.getenv("AXIOM_UI_STREAM_REFRESH_SEC", "2.0") or "2.0"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _envelope(payload_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": payload_type,
        "generated_at": _utc_now(),
        "payload": payload,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "axiom-ui-api",
        "generated_at": _utc_now(),
    }


@app.get("/api/home")
def home(limit: int = 5) -> dict[str, Any]:
    return _envelope("home", get_axiom_home_payload(limit=max(1, int(limit))))


@app.get("/api/top-opportunities")
def top_opportunities(limit: int = 5) -> dict[str, Any]:
    return _envelope("top_opportunities", get_top_opportunities_payload(limit=max(1, int(limit))))


@app.get("/api/advisory")
def advisory(limit: int = 25) -> dict[str, Any]:
    return _envelope("advisory", get_advisory_payload(limit=max(1, int(limit))))


@app.get("/api/review-queue")
def review_queue(limit: int = 50) -> dict[str, Any]:
    return _envelope("review_queue", get_review_queue_payload(limit=max(1, int(limit))))


@app.get("/api/system-health")
def system_health() -> dict[str, Any]:
    return _envelope("system_health", get_system_health_payload())


async def _stream_home(websocket: WebSocket, limit: int) -> None:
    await websocket.accept()
    try:
        while True:
            payload = _envelope("home", get_axiom_home_payload(limit=max(1, int(limit))))
            await websocket.send_text(json.dumps(payload, default=str))
            await asyncio.sleep(_REFRESH_SEC)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/home")
async def ws_home(websocket: WebSocket) -> None:
    limit_raw = websocket.query_params.get("limit", "5")
    try:
        limit = int(limit_raw)
    except Exception:
        limit = 5
    await _stream_home(websocket, limit)
