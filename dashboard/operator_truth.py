from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config as cfg
from core.paths import data_root, desk_logs_dir, logs_dir, trade_db_path

INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        return dict(value["payload"])
    return value if isinstance(value, dict) else {}


def _jsonl(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _latest_named(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.exists():
        return direct
    try:
        matches = [p for p in root.rglob(name) if p.is_file()]
    except OSError:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime, default=None)


def load_market_state() -> dict[str, Any]:
    path = _latest_named(data_root(), "market_state_engine_v1.json")
    payload = _json(path) if path else {}
    if payload:
        payload["_path"] = str(path)
    return payload


def _instrument_authority() -> tuple[Path | None, dict[str, int]]:
    raw = _latest_named(data_root(), "instruments.raw.json")
    if raw is None:
        return None, {}
    try:
        rows = json.loads(raw.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return raw, {}
    aliases = {"NIFTY": {"NIFTY", "NIFTY 50"}, "BANKNIFTY": {"BANKNIFTY", "NIFTY BANK"}, "SENSEX": {"SENSEX"}}
    tokens: dict[str, int] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("tradingsymbol") or row.get("name") or "").strip().upper()
        try:
            token = int(row.get("instrument_token"))
        except (TypeError, ValueError):
            continue
        for symbol, names in aliases.items():
            if name in names and symbol not in tokens:
                tokens[symbol] = token
    return raw, tokens


def load_index_series(*, desk_id: str, lookback_sec: int = 7200, max_points: int = 600) -> dict[str, list[dict[str, float]]]:
    _, tokens = _instrument_authority()
    result = {symbol: [] for symbol in INDEX_SYMBOLS}
    db = trade_db_path(desk_id)
    if not db.exists() or not tokens:
        return result
    now = datetime.now(timezone.utc).timestamp()
    try:
        conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True, timeout=0.5)
        for symbol, token in tokens.items():
            rows = conn.execute(
                "SELECT timestamp_epoch,last_price FROM ticks WHERE instrument_token=? AND timestamp_epoch>=? AND timestamp_epoch<=? AND last_price IS NOT NULL ORDER BY timestamp_epoch ASC",
                (token, now - float(lookback_sec), now),
            ).fetchall()
            if len(rows) > max_points:
                stride = max(1, len(rows) // max_points)
                rows = rows[::stride][-max_points:]
            result[symbol] = [{"ts": float(ts), "price": float(price)} for ts, price in rows if ts is not None and price is not None]
        conn.close()
    except (sqlite3.Error, OSError):
        return {symbol: [] for symbol in INDEX_SYMBOLS}
    return result


def load_strategy_monitor(*, desk_id: str) -> list[dict[str, Any]]:
    candidates = _jsonl(desk_logs_dir(desk_id) / "candidates.jsonl")
    lifecycle = _jsonl(logs_dir() / "trade_lifecycle.jsonl")
    activity: dict[str, dict[str, Any]] = {}
    for row in candidates:
        strategy = str(row.get("strategy") or row.get("strategy_id") or "").strip()
        if not strategy:
            continue
        item = activity.setdefault(strategy, {"strategy": strategy, "candidates": 0, "last_status": "CANDIDATE", "last_reason": ""})
        item["candidates"] += 1
    for row in lifecycle:
        strategy = str(row.get("strategy") or row.get("strategy_id") or "").strip()
        if not strategy:
            continue
        item = activity.setdefault(strategy, {"strategy": strategy, "candidates": 0, "last_status": "OBSERVED", "last_reason": ""})
        item["last_status"] = str(row.get("status") or row.get("stage") or "OBSERVED").upper()
        item["last_reason"] = str(row.get("reason") or row.get("entry_block_code") or "")
    return sorted(activity.values(), key=lambda x: (-int(x["candidates"]), x["strategy"]))


def pipeline_pulse(*, feed_status: str, risk_status: str, market_state: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, str]]:
    summary = metrics.get("summary") or {}
    sources = metrics.get("source_status") or {}
    funnel = summary.get("latest_pipeline_funnel") or {}
    surfaced = int(summary.get("advisory_conversion_denominator") or 0)
    def state(ok: bool, unknown: bool = False) -> str:
        return "UNKNOWN" if unknown else ("LIVE" if ok else "BLOCKED")
    feed_good = str(feed_status).lower() in {"ok", "live", "fresh", "healthy", "pass"}
    risk_good = str(risk_status).lower() in {"ok", "live", "fresh", "healthy", "pass", "safe"}
    return [
        {"stage": "KITE FEED", "state": state(feed_good), "detail": str(feed_status).upper()},
        {"stage": "NORMALIZE", "state": state(False, not bool(sources)), "detail": "runtime evidence" if sources else "no authoritative artifact"},
        {"stage": "MARKET STATE", "state": state(bool(market_state)), "detail": str(market_state.get("verdict") or "MISSING")},
        {"stage": "STRATEGIES", "state": state(bool(sources.get("candidates_stream", {}).get("exists") or sources.get("trade_lifecycle", {}).get("exists"))), "detail": "runtime streams"},
        {"stage": "CANDIDATES", "state": state(bool(sources.get("candidates_stream", {}).get("exists") or funnel)), "detail": str(summary.get("candidate_pool_latest", 0))},
        {"stage": "RANK", "state": state(bool(sources.get("trade_lifecycle", {}).get("exists") or funnel)), "detail": str(summary.get("ranked_candidate_count", 0))},
        {"stage": "RISK", "state": state(risk_good), "detail": str(risk_status).upper()},
        {"stage": "ADVISORY", "state": state(bool(sources.get("suggestions", {}).get("exists") or sources.get("top_opportunities", {}).get("exists"))), "detail": str(surfaced)},
    ]
