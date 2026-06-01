from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from config import config as cfg
from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_LIVE_WORKLOAD_SCHEMA_VERSION = 1
RUNTIME_LIVE_WORKLOAD_SOURCE = "runtime_live_workload_evidence_v1"
RUNTIME_LIVE_WORKLOAD_FILENAME = "live_workload_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def build_live_workload_payload(
    *,
    execution_mode: str | None,
    market_open: bool | None,
    market_data_list: list[Mapping[str, Any]] | None,
    feed_runtime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper() or "SIM"
    feed_rt = _as_mapping(feed_runtime)
    subscribed_tokens_count = _safe_int(feed_rt.get("subscribed_tokens_count"))
    subscribed_option_tokens_count = _safe_int(feed_rt.get("subscribed_option_tokens_count"))

    configured_strikes_around_by_symbol = dict(getattr(cfg, "STRIKES_AROUND_BY_SYMBOL", {}) or {})
    configured_strikes_around_default = int(getattr(cfg, "STRIKES_AROUND", 6) or 6)

    depth_strikes_around_by_symbol = dict(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {})
    depth_strikes_around_default = int(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6) or 6)
    depth_max_tokens = _safe_int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", None))

    option_chain_rows_by_symbol: Counter[str] = Counter()
    option_chain_total_rows = 0
    for row in list(market_data_list or []):
        md = _as_mapping(row)
        symbol = str(md.get("symbol") or "").strip().upper()
        chain = md.get("option_chain")
        if not symbol or not isinstance(chain, list):
            continue
        count = len(chain)
        option_chain_rows_by_symbol[symbol] += count
        option_chain_total_rows += count

    wide_live_universe_warning = False
    if mode == "LIVE":
        for sym, around in configured_strikes_around_by_symbol.items():
            try:
                if int(around) >= 30:
                    wide_live_universe_warning = True
                    break
            except Exception:
                continue

    payload = {
        "schema_version": RUNTIME_LIVE_WORKLOAD_SCHEMA_VERSION,
        "source": RUNTIME_LIVE_WORKLOAD_SOURCE,
        "execution_mode": mode,
        "market_open": bool(market_open) if market_open is not None else None,
        "configured_strikes_around_default": configured_strikes_around_default,
        "configured_strikes_around_by_symbol": configured_strikes_around_by_symbol,
        "depth_subscription_strikes_around_default": depth_strikes_around_default,
        "depth_subscription_strikes_around_by_symbol": depth_strikes_around_by_symbol,
        "depth_subscription_max_tokens": depth_max_tokens,
        "option_chain_rows_by_symbol": dict(option_chain_rows_by_symbol),
        "option_chain_total_rows": int(option_chain_total_rows),
        "subscribed_tokens_count": subscribed_tokens_count,
        "subscribed_option_tokens_count": subscribed_option_tokens_count,
        "wide_live_universe_warning": bool(wide_live_universe_warning),
        "generated_epoch": float(time.time()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_live_workload_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    # Contract: write both repo-local `logs/` and runtime `.runtime/` latest artifacts.
    # For backward compatibility, also mirror into runtime `logs_dir()` (usually `.runtime/logs`).
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_LIVE_WORKLOAD_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_LIVE_WORKLOAD_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_LIVE_WORKLOAD_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_LIVE_WORKLOAD_FILENAME",
    "build_live_workload_payload",
    "write_live_workload_latest",
]

