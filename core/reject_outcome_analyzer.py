from __future__ import annotations

import argparse
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from config import config as cfg
from core.learning_paths import rejected_candidates_paths
from core.market_data import get_option_candles_or_snapshots
from core.option_token_resolver import resolve_option_token
from core.paths import logs_dir
from core.review_queue import (
    QUEUE_PATH,
    QUICK_QUEUE_PATH,
    SCALP_QUEUE_PATH,
    TARGET_POINTS_QUEUE_PATH,
    ZERO_HERO_QUEUE_PATH,
    load_queue_rows,
)
from core.time_utils import is_market_open_ist, now_utc_epoch

IST = ZoneInfo("Asia/Kolkata")
_OUTCOME_COLUMNS = ("time_ms", "open", "high", "low", "close", "volume")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"none", "null", "nan"}:
                return None
            return float(text)
        return float(value)
    except Exception:
        return None


def _coerce_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            val = float(value)
            if val <= 0:
                return None
            if val >= 10_000_000_000:
                return int(val)
            return int(val * 1000.0)
        text = str(value).strip()
        if not text:
            return None
        try:
            return _coerce_epoch_ms(float(text))
        except Exception:
            pass
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000.0)
    except Exception:
        return None


def _normalize_option_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return None


def _is_long_side(side: str | None) -> bool:
    side_text = str(side or "").strip().upper()
    if side_text.startswith("SELL") or side_text in {"SHORT"}:
        return False
    return True


def _to_date_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _normalize_reject_record(raw: dict, source: str) -> dict | None:
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        return None
    ts_ms = _coerce_epoch_ms(
        raw.get("reject_ts_epoch")
        or raw.get("timestamp_epoch_ms")
        or raw.get("timestamp_epoch")
        or raw.get("ts_epoch")
        or raw.get("timestamp")
        or raw.get("ts_ist")
        or raw.get("timestamp_utc_iso")
    )
    if ts_ms is None:
        return None
    strike = _safe_float(raw.get("strike"))
    option_type = _normalize_option_type(raw.get("option_type") or raw.get("type") or raw.get("right"))
    side = str(raw.get("trade_side") or raw.get("direction") or raw.get("side") or "BUY").strip().upper()
    entry = _safe_float(raw.get("intended_entry") or raw.get("entry") or raw.get("entry_price") or raw.get("option_ltp"))
    target = _safe_float(raw.get("target") or raw.get("target_price"))
    stop = _safe_float(raw.get("stop") or raw.get("stop_price") or raw.get("stop_loss"))
    if entry is None or target is None or stop is None:
        return None
    reject_reason = str(raw.get("reject_reason") or raw.get("reason_code") or raw.get("reason") or "unknown_reject").strip()
    if not reject_reason:
        reject_reason = "unknown_reject"
    expiry = str(raw.get("expiry_date") or raw.get("expiry") or "").strip() or None
    tradingsymbol = str(raw.get("tradingsymbol") or "").strip() or None
    instrument_token = None
    try:
        tok = raw.get("instrument_token")
        if tok is not None and str(tok).strip():
            instrument_token = int(tok)
    except Exception:
        instrument_token = None
    reject_key = str(raw.get("reject_id") or raw.get("candidate_id") or raw.get("blocked_id") or raw.get("trade_key") or "").strip()
    if not reject_key:
        digest = hashlib.sha256(
            f"{symbol}|{expiry}|{strike}|{option_type}|{side}|{ts_ms}|{entry}|{target}|{stop}|{reject_reason}".encode("utf-8")
        ).hexdigest()[:20]
        reject_key = f"rej_{digest}"
    return {
        "reject_id": reject_key,
        "source": source,
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "side": side,
        "reject_ts_epoch_ms": int(ts_ms),
        "intended_entry": float(entry),
        "target": float(target),
        "stop": float(stop),
        "reject_reason": reject_reason,
        "expiry": expiry,
        "tradingsymbol": tradingsymbol,
        "instrument_token": instrument_token,
    }


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _load_blocked_rejects(date_key: str) -> list[dict]:
    rows: list[dict] = []
    for path in rejected_candidates_paths():
        for raw in _read_jsonl(path):
            rec = _normalize_reject_record(raw, source="decision_telemetry")
            if rec is None:
                continue
            if _to_date_key(int(rec["reject_ts_epoch_ms"])) == date_key:
                rows.append(rec)
    return rows


def _load_review_queue_rejects(date_key: str) -> list[dict]:
    rows: list[dict] = []
    queue_paths = [QUEUE_PATH, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH, TARGET_POINTS_QUEUE_PATH]
    for path in queue_paths:
        for raw in load_queue_rows(path, rewrite_healed=False):
            status = str(raw.get("status") or "").strip().upper()
            permission = str(raw.get("permission") or "").strip().upper()
            reject_reason = str(raw.get("reject_reason") or "").strip()
            if not (reject_reason or status in {"REJECTED", "BLOCKED"} or permission in {"BLOCK", "ADVISORY_ONLY"}):
                continue
            rec = _normalize_reject_record(raw, source="review_queue")
            if rec is None:
                continue
            if not reject_reason:
                rec["reject_reason"] = "review_queue_blocked"
            if _to_date_key(int(rec["reject_ts_epoch_ms"])) == date_key:
                rows.append(rec)
    return rows


def _load_rejected_trades_for_date(date_key: str) -> list[dict]:
    merged: list[dict] = []
    seen = set()
    for rec in _load_blocked_rejects(date_key) + _load_review_queue_rejects(date_key):
        rid = str(rec.get("reject_id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        merged.append(rec)
    merged.sort(key=lambda row: int(row.get("reject_ts_epoch_ms") or 0))
    return merged


def _empty_candle_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_OUTCOME_COLUMNS))


def _normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_candle_df()
    out = df.copy()
    if "time_ms" not in out.columns:
        out["time_ms"] = None
    if "high" not in out.columns and "close" in out.columns:
        out["high"] = out["close"]
    if "low" not in out.columns and "close" in out.columns:
        out["low"] = out["close"]
    if "open" not in out.columns and "close" in out.columns:
        out["open"] = out["close"]
    for col in _OUTCOME_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out["time_ms"] = pd.to_numeric(out["time_ms"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["time_ms", "high", "low", "close"])
    if out.empty:
        return _empty_candle_df()
    out = out.sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
    return out[list(_OUTCOME_COLUMNS)]


def _resolve_instrument_token(rec: dict) -> int | None:
    token = rec.get("instrument_token")
    try:
        if token is not None and str(token).strip():
            return int(token)
    except Exception:
        pass
    symbol = str(rec.get("symbol") or "").upper()
    expiry = str(rec.get("expiry") or "").strip()
    strike = _safe_float(rec.get("strike"))
    option_type = _normalize_option_type(rec.get("option_type"))
    if not (symbol and expiry and strike is not None and option_type):
        return None
    try:
        resolved = resolve_option_token(symbol, expiry, strike, option_type)
    except Exception:
        resolved = None
    if isinstance(resolved, dict):
        tok = resolved.get("instrument_token")
        try:
            return int(tok) if tok is not None else None
        except Exception:
            return None
    return None


def _fetch_trade_candles(
    rec: dict,
    *,
    start_ms: int,
    end_ms: int,
    source: str,
    interval: str,
) -> pd.DataFrame:
    src = str(source or "kite").strip().lower()
    token = _resolve_instrument_token(rec)
    if src == "market_data":
        trade_row = {
            "instrument_token": token,
            "tradingsymbol": rec.get("tradingsymbol"),
            "symbol": rec.get("symbol"),
        }
        return _normalize_candles(get_option_candles_or_snapshots(trade_row, interval, start_ms, end_ms))

    # Default source uses the same broker-backed historical API via kite_client.
    if token is None or token <= 0:
        trade_row = {
            "instrument_token": token,
            "tradingsymbol": rec.get("tradingsymbol"),
            "symbol": rec.get("symbol"),
        }
        return _normalize_candles(get_option_candles_or_snapshots(trade_row, interval, start_ms, end_ms))
    try:
        from core.kite_client import kite_client
    except Exception:
        return _empty_candle_df()
    try:
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        from_dt = datetime.fromtimestamp(float(start_ms) / 1000.0, tz=timezone.utc).astimezone(ist_tz)
        to_dt = datetime.fromtimestamp(float(end_ms) / 1000.0, tz=timezone.utc).astimezone(ist_tz)
        candles = kite_client.historical_data(int(token), from_dt, to_dt, interval=interval) or []
    except Exception:
        candles = []
    rows = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        ts_ms = _coerce_epoch_ms(candle.get("date") or candle.get("ts"))
        open_px = _safe_float(candle.get("open"))
        high_px = _safe_float(candle.get("high"))
        low_px = _safe_float(candle.get("low"))
        close_px = _safe_float(candle.get("close"))
        volume = _safe_float(candle.get("volume"))
        if ts_ms is None or open_px is None or high_px is None or low_px is None or close_px is None:
            continue
        rows.append(
            {
                "time_ms": int(ts_ms),
                "open": float(open_px),
                "high": float(high_px),
                "low": float(low_px),
                "close": float(close_px),
                "volume": float(volume if volume is not None else 0.0),
            }
        )
    return _normalize_candles(pd.DataFrame(rows))


def _evaluate_reject_with_candles(rec: dict, candles_df: pd.DataFrame, lookahead_minutes: int) -> dict:
    start_ms = int(rec["reject_ts_epoch_ms"])
    end_ms = int(start_ms + max(1, int(lookahead_minutes)) * 60 * 1000)
    candles = _normalize_candles(candles_df)
    if candles.empty:
        return {
            "outcome": "NO_HIT",
            "outcome_reason": "NO_CANDLES",
            "resolved_ts_epoch_ms": None,
            "mfe_points": None,
            "mae_points": None,
        }

    entry = float(rec["intended_entry"])
    target = float(rec["target"])
    stop = float(rec["stop"])
    is_long = _is_long_side(rec.get("side"))

    window = candles[(candles["time_ms"] >= start_ms) & (candles["time_ms"] <= end_ms)]
    if window.empty:
        return {
            "outcome": "NO_HIT",
            "outcome_reason": "NO_CANDLES_IN_WINDOW",
            "resolved_ts_epoch_ms": None,
            "mfe_points": None,
            "mae_points": None,
        }

    mfe = None
    mae = None
    outcome = "NO_HIT"
    outcome_reason = "WINDOW_EXPIRED"
    resolved_ts = None

    for row in window.itertuples(index=False):
        high = _safe_float(getattr(row, "high", None))
        low = _safe_float(getattr(row, "low", None))
        ts_ms = int(getattr(row, "time_ms"))
        if high is None or low is None:
            continue

        if is_long:
            fav = high - entry
            adv = low - entry
            target_hit = high >= target
            sl_hit = low <= stop
        else:
            fav = entry - low
            adv = entry - high
            target_hit = low <= target
            sl_hit = high >= stop

        mfe = fav if mfe is None else max(mfe, fav)
        mae = adv if mae is None else min(mae, adv)

        if target_hit and sl_hit:
            # Intrabar order cannot be inferred from OHLC; fail closed.
            outcome = "NO_HIT"
            outcome_reason = "AMBIGUOUS_SAME_CANDLE"
            resolved_ts = ts_ms
            break
        if target_hit:
            outcome = "HIT_TARGET"
            outcome_reason = "TARGET_FIRST"
            resolved_ts = ts_ms
            break
        if sl_hit:
            outcome = "HIT_SL"
            outcome_reason = "SL_FIRST"
            resolved_ts = ts_ms
            break

    return {
        "outcome": outcome,
        "outcome_reason": outcome_reason,
        "resolved_ts_epoch_ms": resolved_ts,
        "mfe_points": (round(float(mfe), 6) if mfe is not None else None),
        "mae_points": (round(float(mae), 6) if mae is not None else None),
    }


def _validate_outcome_row(row: dict) -> dict:
    required = (
        "reject_id",
        "symbol",
        "reject_ts_epoch_ms",
        "intended_entry",
        "target",
        "stop",
        "reject_reason",
        "outcome",
    )
    for key in required:
        if row.get(key) is None:
            raise ValueError(f"missing_required_field:{key}")
    return row


def _outcomes_path() -> Path:
    return Path(
        str(
            getattr(
                cfg,
                "REJECT_OUTCOMES_LOG_PATH",
                str(logs_dir() / "rejected_trade_outcomes.jsonl"),
            )
        )
    )


def _summary_path(day: str) -> Path:
    configured = str(getattr(cfg, "REJECT_OUTCOMES_SUMMARY_PATH", "") or "").strip()
    if configured:
        path = Path(configured)
        if path.suffix.lower() == ".json":
            return path
        return path / f"rejected_trade_outcomes_summary_{day}.json"
    return logs_dir() / f"rejected_trade_outcomes_summary_{day}.json"


def _atomic_write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _summarize_by_reason(rows: list[dict]) -> dict[str, dict]:
    bucket: dict[str, dict[str, Any]] = {}
    for row in rows:
        reason = str(row.get("reject_reason") or "unknown_reject")
        ref = bucket.setdefault(reason, {"count": 0, "hit_target_count": 0, "mfe": [], "mae": []})
        ref["count"] += 1
        if str(row.get("outcome")) == "HIT_TARGET":
            ref["hit_target_count"] += 1
        mfe = _safe_float(row.get("mfe_points"))
        mae = _safe_float(row.get("mae_points"))
        if mfe is not None:
            ref["mfe"].append(float(mfe))
        if mae is not None:
            ref["mae"].append(float(mae))
    out: dict[str, dict] = {}
    for reason, ref in bucket.items():
        count = int(ref["count"])
        mfe_vals = ref.get("mfe") or []
        mae_vals = ref.get("mae") or []
        out[reason] = {
            "count": count,
            "hit_rate": (float(ref["hit_target_count"]) / float(count)) if count > 0 else 0.0,
            "avg_mfe": (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None,
            "avg_mae": (sum(mae_vals) / len(mae_vals)) if mae_vals else None,
        }
    return out


def _parse_date(date_value: str | date_cls | datetime | None) -> str:
    if isinstance(date_value, datetime):
        return date_value.date().isoformat()
    if isinstance(date_value, date_cls):
        return date_value.isoformat()
    if date_value is None:
        return datetime.now(tz=IST).date().isoformat()
    text = str(date_value).strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def analyze_rejected_trades(date, lookahead_minutes: int = 30) -> dict:
    day = _parse_date(date)
    lookahead_min = max(1, int(lookahead_minutes))
    if is_market_open_ist() and not bool(getattr(cfg, "REJECT_OUTCOME_ALLOW_MARKET_HOURS", False)):
        return {
            "date": day,
            "status": "SKIPPED_MARKET_HOURS",
            "reason": "market_open_guard",
            "lookahead_minutes": lookahead_min,
            "analyzed": 0,
            "summary_by_reject_reason": {},
            "output_path": str(_outcomes_path()),
        }

    source = str(getattr(cfg, "REJECT_OUTCOME_CANDLE_SOURCE", "kite") or "kite").strip().lower()
    interval = str(getattr(cfg, "REJECT_OUTCOME_CANDLE_INTERVAL", "minute") or "minute").strip()
    rejects = _load_rejected_trades_for_date(day)
    outcomes: list[dict] = []

    for rec in rejects:
        reject_ts_ms = int(rec["reject_ts_epoch_ms"])
        end_ms = int(reject_ts_ms + lookahead_min * 60 * 1000)
        candles = _fetch_trade_candles(
            rec,
            start_ms=reject_ts_ms,
            end_ms=end_ms,
            source=source,
            interval=interval,
        )
        eval_out = _evaluate_reject_with_candles(rec, candles, lookahead_min)
        row = dict(rec)
        row.update(eval_out)
        row["lookahead_minutes"] = lookahead_min
        row["candle_source"] = source
        row["candle_interval"] = interval
        row["analyzed_ts_epoch"] = float(now_utc_epoch())
        row["analysis_date"] = day
        row["reject_ts_utc"] = datetime.fromtimestamp(float(reject_ts_ms) / 1000.0, tz=timezone.utc).isoformat()
        outcomes.append(_validate_outcome_row(row))

    output_path = _outcomes_path()
    existing = _read_jsonl(output_path)
    key_fields = {(str(row.get("analysis_date")), str(row.get("reject_id"))) for row in outcomes}
    keep_rows = [
        row
        for row in existing
        if (str(row.get("analysis_date")), str(row.get("reject_id"))) not in key_fields
    ]
    merged = keep_rows + outcomes
    merged.sort(key=lambda row: float(row.get("reject_ts_epoch_ms") or 0.0))
    _atomic_write_jsonl(output_path, merged)

    summary = _summarize_by_reason(outcomes)
    summary_payload = {
        "date": day,
        "lookahead_minutes": lookahead_min,
        "analyzed": len(outcomes),
        "summary_by_reject_reason": summary,
        "generated_ts_epoch": float(now_utc_epoch()),
    }
    _atomic_write_json(_summary_path(day), summary_payload)
    return {
        "date": day,
        "status": "OK",
        "lookahead_minutes": lookahead_min,
        "candle_source": source,
        "candle_interval": interval,
        "analyzed": len(outcomes),
        "summary_by_reject_reason": summary,
        "output_path": str(output_path),
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze post-hoc outcomes for rejected trades.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument("--lookahead-minutes", type=int, default=30, help="Lookahead window in minutes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    result = analyze_rejected_trades(args.date, lookahead_minutes=args.lookahead_minutes)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
