import json
from pathlib import Path

from config import config as cfg
from core.time_utils import now_ist, now_utc_epoch


def gate_status_path(desk_id: str | None = None) -> Path:
    desk = desk_id or getattr(cfg, "DESK_ID", "DEFAULT")
    return Path(f"logs/desks/{desk}/gate_status.jsonl")


def build_gate_status_record(
    market_data: dict,
    gate_allowed,
    gate_family,
    gate_reasons,
    stage: str,
) -> dict:
    data = market_data or {}
    regime_probs = data.get("regime_probs") or {}
    max_prob = max(regime_probs.values()) if regime_probs else None
    indicator_stale_sec = float(getattr(cfg, "INDICATOR_STALE_SEC", 120))
    payload = {
        "symbol": data.get("symbol"),
        "stage": stage,
        "cycle_id": data.get("cycle_id"),
        "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")),
        "kite_use_api": bool(getattr(cfg, "KITE_USE_API", True)),
        "ltp": data.get("ltp"),
        "ltp_source": data.get("ltp_source"),
        "ltp_ts_epoch": data.get("ltp_ts_epoch"),
        "indicators_ok": bool(data.get("indicators_ok", False)),
        "indicators_age_sec": data.get("indicators_age_sec"),
        "indicator_stale_sec": indicator_stale_sec,
        "primary_regime": data.get("primary_regime") or data.get("regime"),
        "regime_probs_max": max_prob,
        # Backward-compatible key retained for existing dashboards.
        "regime_prob_max": max_prob,
        "regime_entropy": data.get("regime_entropy"),
        "unstable_regime_flag": bool(data.get("unstable_regime_flag", False)),
        "unstable_reasons": list(data.get("unstable_reasons") or []),
        "gate_allowed": bool(gate_allowed),
        "gate_family": gate_family,
        "gate_reasons": list(gate_reasons or []),
    }
    if (payload.get("indicators_ok") is False) or (payload.get("indicators_age_sec") is None):
        payload.update(
            {
                "indicator_last_update_epoch": data.get("indicator_last_update_epoch"),
                "ohlc_bars_count": data.get("ohlc_bars_count"),
                "ohlc_last_bar_epoch": data.get("ohlc_last_bar_epoch"),
                "compute_indicators_error": data.get("compute_indicators_error"),
                "missing_inputs": list(data.get("missing_inputs") or []),
            }
        )
    return payload


def append_gate_status(record: dict, desk_id: str | None = None) -> None:
    path = gate_status_path(desk_id=desk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        **(record or {}),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")
