from __future__ import annotations

from pathlib import Path
from typing import Any

from core.events import read_events, write_json_atomic
from core.paths import logs_dir


def build_recon(events: list[dict[str, Any]]) -> dict[str, Any]:
    fills: list[dict[str, Any]] = []
    for row in events:
        if str(row.get("type") or "") != "fill":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        fills.append(
            {
                "ts": row.get("ts"),
                "order_id": str(payload.get("order_id") or ""),
                "trade_id": str(payload.get("trade_id") or ""),
                "symbol": str(payload.get("symbol") or ""),
                "side": str(payload.get("side") or "").upper(),
                "qty": float(payload.get("qty") or 0.0),
                "price": float(payload.get("price") or 0.0),
                "run_id": str(payload.get("run_id") or ""),
                "desk_id": str(payload.get("desk_id") or ""),
                "mode": str(payload.get("mode") or "").upper(),
            }
        )

    symbols = sorted({row["symbol"] for row in fills if row.get("symbol")})
    recon = {
        "status": "ok" if fills else "empty",
        "trade_count": len(fills),
        "symbols": symbols,
        "total_qty": float(sum(abs(float(row.get("qty") or 0.0)) for row in fills)),
        "trades": fills,
    }
    return recon


def recon_path() -> Path:
    return logs_dir() / "recon.json"


def project_from_events(*, run_id: str | None = None) -> dict[str, Any]:
    events = read_events(run_id=run_id)
    recon = build_recon(events)
    write_json_atomic(recon_path(), recon)
    return recon
