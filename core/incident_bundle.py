from __future__ import annotations

import json
import logging
import re
import shutil
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.advisory_schema import AdvisorySchemaError, deserialize_advisory_row
from core.events import write_json_atomic
from core.learning_paths import canonical_suggestions_log_path
from core.paths import data_root, repo_root, runtime_dir, logs_dir

logger = logging.getLogger(__name__)

BUNDLE_VERSION = 1
DEFAULT_WINDOW_MINUTES = 20
DEFAULT_MAX_MATCHING_ROWS = 2000
INCIDENT_KEYWORDS = (
    "STALE_OPTION_LTP",
    "PRICE_MISMATCH",
    "NO_TOKEN",
    "NO_LIVE_OPTION_FEED",
    "entry_status",
    "quote_age_sec",
    "token",
    "advisory",
    "blocker",
)
LOG_FILENAMES = ("main.log", "scheduler.log", "streamlit.log")


def default_incident_output_dir() -> Path:
    return repo_root() / "runtime" / "incidents"


def _now_epoch(now_epoch: float | None = None) -> float:
    return float(now_epoch if now_epoch is not None else time.time())


def _iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _norm_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _norm_upper(value: Any) -> str | None:
    text = _norm_text(value)
    return text.upper() if text else None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _safe_json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _read_json_file(path: Path) -> tuple[dict[str, Any] | list[Any] | None, dict[str, Any]]:
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "parse_ok": False,
        "missing": not path.exists(),
        "error": None,
    }
    if not path.exists():
        return None, meta
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return None, meta
    meta["parse_ok"] = True
    return payload, meta


def _copy_raw_file(path: Path, raw_dir: Path, dest_name: str | None = None) -> str | None:
    if not path.exists():
        return None
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / (dest_name or path.name)
    try:
        shutil.copy2(path, target)
    except Exception as exc:
        logger.warning("incident_bundle_raw_copy_failed path=%s error=%s", path, exc)
        return None
    return str(target)


def _write_raw_json(raw_dir: Path, name: str, payload: Any) -> str | None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("incident_bundle_raw_json_write_failed path=%s error=%s", path, exc)
        return None
    return str(path)


def _write_raw_text(raw_dir: Path, name: str, text: str) -> str | None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / name
    try:
        path.write_text(str(text), encoding="utf-8")
    except Exception as exc:
        logger.warning("incident_bundle_raw_text_write_failed path=%s error=%s", path, exc)
        return None
    return str(path)


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _tail_jsonl_rows(path: Path, limit: int = DEFAULT_MAX_MATCHING_ROWS) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, int(limit)))
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return list(rows)


def _row_epoch(row: dict[str, Any]) -> float | None:
    for key in (
        "freshness_now_epoch",
        "timestamp_epoch",
        "ts_epoch",
        "timestamp_epoch_ms",
        "last_seen_epoch",
    ):
        value = _safe_float(row.get(key))
        if value is None:
            continue
        if "ms" in key and value > 1e12:
            value = value / 1000.0
        return value
    for key in ("timestamp", "last_seen_ts", "ts_utc", "created_at", "updated_at"):
        text = _norm_text(row.get(key))
        if not text:
            continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
    return None


def _row_matches(row: dict[str, Any], *, symbol: str, trade_id: str | None) -> bool:
    row_symbol = _norm_upper(row.get("symbol"))
    row_trade_id = _norm_text(row.get("trade_id")) or _norm_text(row.get("advisory_id"))
    if trade_id:
        return row_trade_id == trade_id
    return row_symbol == _norm_upper(symbol)


def _matching_advisory_rows(path: Path, *, symbol: str, trade_id: str | None) -> list[dict[str, Any]]:
    matches = [row for row in _tail_jsonl_rows(path) if _row_matches(row, symbol=symbol, trade_id=trade_id)]
    matches.sort(key=lambda row: (_row_epoch(row) or 0.0, _norm_text(row.get("trade_id")) or ""), reverse=True)
    return matches


def _deserialize_row_best_effort(row: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    try:
        return deserialize_advisory_row(row, allow_legacy=True), None
    except AdvisorySchemaError as exc:
        return dict(row), str(exc)


def _select_freshness_decision(payload: dict[str, Any], *, symbol: str, trade_id: str | None) -> dict[str, Any]:
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), dict) else {}
    symbol_block = decisions.get(str(symbol).upper())
    if not isinstance(symbol_block, dict):
        return {}
    prioritized = ("option_entry", "option_quote")
    if trade_id:
        for _, decision in symbol_block.items():
            if isinstance(decision, dict) and str(decision.get("trade_id") or "").strip() == str(trade_id):
                return dict(decision)
    for key in prioritized:
        if isinstance(symbol_block.get(key), dict):
            return dict(symbol_block[key])
    for decision in symbol_block.values():
        if isinstance(decision, dict):
            return dict(decision)
    return {}


def _select_token_resolution_row(payload: Any, *, symbol: str) -> dict[str, Any]:
    symbol_key = str(symbol).upper()
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and str(row.get("symbol") or "").upper() == symbol_key:
                return dict(row)
    if isinstance(payload, dict):
        direct = payload.get(symbol_key) or payload.get(symbol)
        if isinstance(direct, dict):
            return dict(direct)
    return {}


def _select_option_chain_rows(payload: Any, *, symbol: str, expiry: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        candidate = payload.get(symbol) or payload.get(str(symbol).upper())
        if isinstance(candidate, list):
            rows = [dict(row) for row in candidate if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [dict(row) for row in payload if isinstance(row, dict) and str(row.get("symbol") or "").upper() == str(symbol).upper()]
    if expiry:
        filtered = []
        for row in rows:
            row_expiry = _norm_text(row.get("expiry") or row.get("expiry_date"))
            if row_expiry == expiry:
                filtered.append(row)
        if filtered:
            return filtered
    return rows


def _dominant_list(values: list[str]) -> str | None:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        return None
    counts = Counter(cleaned)
    return counts.most_common(1)[0][0]


def _parse_line_epoch(line: str) -> float | None:
    text = str(line or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            for key in ("ts_epoch", "timestamp_epoch", "now_epoch"):
                value = _safe_float(payload.get(key))
                if value is not None:
                    return value
            for key in ("ts", "timestamp", "ts_utc"):
                raw = _norm_text(payload.get(key))
                if not raw:
                    continue
                try:
                    return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2}[T ][0-9:.+-]+Z?)", text)
    if match:
        try:
            return datetime.fromisoformat(match.group(1).replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    return None


def _text_has_symbol(text: str, symbol: str) -> bool:
    symbol_key = str(symbol or "").strip().upper()
    if not symbol_key:
        return False
    upper = str(text or "").upper()
    return re.search(rf"(?<![A-Z0-9_]){re.escape(symbol_key)}(?![A-Z0-9_])", upper) is not None


def _collect_log_snippets(
    *,
    symbol: str,
    trade_id: str | None,
    window_minutes: int,
    now_epoch: float,
    process_logs_dir: Path,
) -> dict[str, Any]:
    snippets: dict[str, list[str]] = {}
    cutoff = float(now_epoch) - (60.0 * max(1, int(window_minutes)))
    symbol_key = str(symbol).upper()
    trade_key = str(trade_id or "").strip()
    keywords = tuple(str(word).upper() for word in INCIDENT_KEYWORDS)
    for filename in LOG_FILENAMES:
        path = process_logs_dir / filename
        if not path.exists():
            continue
        matched: deque[str] = deque(maxlen=50)
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    raw = line.rstrip("\n")
                    upper = raw.upper()
                    symbol_match = _text_has_symbol(raw, symbol_key)
                    trade_match = trade_key and trade_key in raw
                    keyword_match = any(word in upper for word in keywords)
                    if not keyword_match:
                        continue
                    if not (symbol_match or trade_match):
                        continue
                    line_epoch = _parse_line_epoch(raw)
                    if line_epoch is not None and line_epoch < cutoff:
                        continue
                    matched.append(raw)
        except Exception as exc:
            snippets[filename] = [f"[log_read_error] {type(exc).__name__}: {exc}"]
            continue
        if matched:
            snippets[filename] = list(matched)
    return {
        "keywords": list(INCIDENT_KEYWORDS),
        "files": snippets,
    }


def _copy_log_snippets(raw_dir: Path, snippets: dict[str, Any]) -> list[str]:
    written: list[str] = []
    files = snippets.get("files") if isinstance(snippets.get("files"), dict) else {}
    for filename, lines in files.items():
        if not isinstance(lines, list):
            continue
        path = _write_raw_text(raw_dir, f"{filename}.snippet.txt", "\n".join(str(line) for line in lines) + "\n")
        if path:
            written.append(path)
    return written


def _extract_blockers(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for field in ("hard_blockers", "soft_penalties", "warnings", "blockers"):
        value = row.get(field)
        if isinstance(value, list):
            for item in value:
                text = _norm_text(item)
                if text and text not in out:
                    out.append(text)
        elif isinstance(value, str):
            text = _norm_text(value)
            if text and text not in out:
                out.append(text)
    return out


def _build_advisory_section(row: dict[str, Any] | None, *, parse_error: str | None) -> dict[str, Any]:
    if not row:
        return {
            "missing": True,
            "parse_error": parse_error,
            "symbol": None,
            "timestamp": None,
            "epoch": None,
            "entry": None,
            "entry_status": None,
            "confidence": None,
            "blockers": [],
            "quote_source": None,
            "quote_age_sec": None,
            "underlying_ltp": None,
            "option_ltp": None,
            "readiness": None,
            "advisory_visible": None,
            "is_executable": None,
            "execution_status": None,
            "instrument_token": None,
            "expiry": None,
            "strike": None,
            "right": None,
            "trade_id": None,
        }
    return {
        "missing": False,
        "parse_error": parse_error,
        "symbol": row.get("symbol"),
        "timestamp": row.get("timestamp") or row.get("last_seen_ts"),
        "epoch": _row_epoch(row),
        "entry": row.get("entry"),
        "entry_status": row.get("entry_status"),
        "confidence": row.get("confidence_final") if row.get("confidence_final") not in (None, "", "None") else row.get("confidence"),
        "blockers": _extract_blockers(row),
        "quote_source": row.get("quote_source"),
        "quote_age_sec": row.get("quote_age_sec"),
        "underlying_ltp": row.get("underlying_ltp") or row.get("spot") or row.get("ltp"),
        "option_ltp": row.get("current_ltp") or row.get("display_entry") or row.get("entry"),
        "readiness": row.get("readiness"),
        "advisory_visible": row.get("advisory_visible"),
        "is_executable": row.get("is_executable"),
        "execution_status": row.get("execution_status"),
        "instrument_token": row.get("instrument_token"),
        "expiry": row.get("expiry_date") or row.get("expiry"),
        "strike": row.get("strike"),
        "right": row.get("option_type") or row.get("right") or row.get("type"),
        "trade_id": row.get("trade_id") or row.get("advisory_id"),
    }


def _build_feed_health_section(feed_debug: dict[str, Any], *, symbol: str, market_open: Any) -> dict[str, Any]:
    symbol_key = str(symbol).upper()
    last_option_tick_ts = None
    if isinstance(feed_debug.get("last_option_tick_ts_by_symbol"), dict):
        last_option_tick_ts = feed_debug.get("last_option_tick_ts_by_symbol", {}).get(symbol_key)
    return {
        "runtime_state": feed_debug.get("feed_runtime_state"),
        "subscribed_tokens_count": feed_debug.get("subscribed_tokens_count"),
        "subscribed_option_tokens_count": feed_debug.get("subscribed_option_tokens_count"),
        "missing_option_tokens_count": feed_debug.get("missing_option_tokens_count"),
        "last_tick_epoch": feed_debug.get("last_tick_epoch_memory"),
        "last_option_tick_epoch": last_option_tick_ts,
        "ws_connected": feed_debug.get("ws_connected"),
        "market_open": market_open,
    }


def _build_freshness_section(decision: dict[str, Any], advisory: dict[str, Any], *, market_open_state: Any) -> dict[str, Any]:
    market_open = _coerce_bool(market_open_state)
    if market_open is None:
        market_open = _coerce_bool(decision.get("market_open"))
    return {
        "now_epoch": decision.get("now_epoch"),
        "quote_epoch": decision.get("quote_epoch"),
        "candle_epoch": decision.get("candle_epoch"),
        "quote_age_sec": advisory.get("quote_age_sec") if advisory.get("quote_age_sec") is not None else decision.get("quote_age_sec"),
        "candle_age_sec": decision.get("candle_age_sec"),
        "stale_threshold_sec": decision.get("threshold_sec"),
        "market_open": market_open,
        "freshness_decision": decision.get("blocker"),
        "freshness_reason": decision.get("reason") or advisory.get("freshness_reason"),
        "selected_source": decision.get("selected_source"),
        "selected_age_sec": decision.get("selected_age_sec"),
    }


def _build_blocker_state_section(current_row: dict[str, Any], previous_row: dict[str, Any] | None) -> dict[str, Any]:
    current_blockers = _extract_blockers(current_row)
    previous_blockers = _extract_blockers(previous_row or {})
    owner = "|".join(
        [
            str(current_row.get("symbol") or "UNKNOWN"),
            str(current_row.get("expiry_date") or current_row.get("expiry") or "UNKNOWN"),
            str(current_row.get("strike") or "UNKNOWN"),
            str(current_row.get("option_type") or current_row.get("right") or current_row.get("type") or "UNKNOWN"),
            str(current_row.get("trade_id") or current_row.get("advisory_id") or "UNKNOWN"),
        ]
    )
    return {
        "current_blockers": current_blockers,
        "previous_blockers": previous_blockers,
        "owner": owner,
        "last_updated_epoch": _row_epoch(current_row),
        "hard_blockers": current_row.get("hard_blockers") or [],
        "soft_penalties": current_row.get("soft_penalties") or [],
        "warnings": current_row.get("warnings") or [],
    }


def _build_option_chain_health_section(rows: list[dict[str, Any]], advisory: dict[str, Any]) -> dict[str, Any]:
    expiry = _norm_text(advisory.get("expiry"))
    strike = _safe_float(advisory.get("strike"))
    if rows:
        sources = [_norm_text(row.get("chain_source")) or _norm_text(row.get("quote_source")) for row in rows]
        ages = [_safe_float(row.get("quote_age_sec")) for row in rows if _safe_float(row.get("quote_age_sec")) is not None]
        atm_available = False
        if strike is not None:
            atm_available = any(_safe_float(row.get("strike")) == strike for row in rows)
        if not atm_available:
            atm_available = any(_safe_float(row.get("moneyness")) == 0.0 for row in rows)
        return {
            "selected_expiry": expiry,
            "option_count": len(rows),
            "atm_available": bool(atm_available),
            "chain_age_sec": min(ages) if ages else None,
            "chain_source": _dominant_list([source for source in sources if source]),
        }
    return {
        "selected_expiry": expiry,
        "option_count": 0,
        "atm_available": False,
        "chain_age_sec": None,
        "chain_source": None,
    }


def _build_token_resolution_section(row: dict[str, Any], advisory: dict[str, Any], *, resolution_epoch: float | None) -> dict[str, Any]:
    option_count = int(row.get("option_count") or row.get("final_option_count") or row.get("resolved_option_count") or 0)
    count_total = int(row.get("count") or row.get("final_count") or row.get("resolved_count") or 0)
    tokens = row.get("tokens") if isinstance(row.get("tokens"), list) else []
    underlying_present = bool(count_total > option_count or len(tokens) > option_count)
    option_present = bool(advisory.get("instrument_token") not in (None, "", "None") or option_count > 0)
    reason = (
        _norm_text(row.get("option_drop_reason"))
        or _norm_text(row.get("option_fail_reason"))
        or _norm_text(row.get("fail_reason"))
    )
    status = "resolved" if option_present else "missing_option_token"
    return {
        "underlying_token_present": underlying_present,
        "option_token_present": option_present,
        "last_resolution_status": status,
        "last_resolution_reason": reason,
        "resolution_epoch": resolution_epoch,
        "expiry": advisory.get("expiry") or row.get("expiry"),
        "strike": advisory.get("strike"),
        "right": advisory.get("right"),
    }


def _incident_summary(
    *,
    advisory: dict[str, Any],
    feed_health: dict[str, Any],
    freshness: dict[str, Any],
    blocker_state: dict[str, Any],
    suggestions_status: dict[str, Any],
    engine_status: dict[str, Any],
) -> dict[str, Any]:
    primary_issue = (
        _dominant_list(blocker_state.get("current_blockers") or [])
        or _norm_text(advisory.get("entry_status"))
        or _norm_text(freshness.get("freshness_reason"))
        or _norm_text(feed_health.get("runtime_state"))
        or _norm_text(suggestions_status.get("primary_blocker"))
        or _norm_text(engine_status.get("primary_blocker"))
        or "NO_DATA"
    )
    status = "ok"
    if advisory.get("missing"):
        status = "missing_advisory"
    elif blocker_state.get("current_blockers") or str(advisory.get("entry_status") or "").upper() not in {"OK", "VALID", "DISPLAYABLE", "NON_EXECUTABLE"}:
        status = "degraded"
    market_open_state = (
        suggestions_status.get("market_open")
        if "market_open" in suggestions_status
        else engine_status.get("market_open")
    )
    return {
        "status": status,
        "primary_issue": primary_issue,
        "market_open_state": market_open_state,
    }


def _render_bundle_text(bundle: dict[str, Any]) -> str:
    meta = bundle.get("bundle_meta") or {}
    incident = bundle.get("incident_summary") or {}
    advisory = bundle.get("advisory") or {}
    freshness = bundle.get("freshness") or {}
    token_state = bundle.get("token_resolution") or {}
    blocker_state = bundle.get("blocker_state") or {}
    feed = bundle.get("feed_health") or {}
    lines = [
        f"Incident bundle v{meta.get('bundle_version')} for {meta.get('symbol')} trade_id={meta.get('trade_id') or '-'}",
        f"Generated: {meta.get('generated_at')} window_minutes={meta.get('window_minutes')}",
        "",
        f"Summary: status={incident.get('status')} primary_issue={incident.get('primary_issue')} market_open={incident.get('market_open_state')}",
        f"Feed: ws_connected={feed.get('ws_connected')} subscribed_option_tokens={feed.get('subscribed_option_tokens_count')} missing_option_tokens={feed.get('missing_option_tokens_count')}",
        f"Advisory: entry={advisory.get('entry')} entry_status={advisory.get('entry_status')} confidence={advisory.get('confidence')} readiness={advisory.get('readiness')}",
        f"Blockers: current={blocker_state.get('current_blockers')} previous={blocker_state.get('previous_blockers')}",
        f"Freshness: reason={freshness.get('freshness_reason')} quote_age_sec={freshness.get('quote_age_sec')} threshold={freshness.get('stale_threshold_sec')}",
        f"Token state: option_token_present={token_state.get('option_token_present')} resolution_status={token_state.get('last_resolution_status')} reason={token_state.get('last_resolution_reason')}",
    ]
    return "\n".join(lines) + "\n"


def build_incident_bundle_payload(
    *,
    symbol: str,
    trade_id: str | None = None,
    minutes: int = DEFAULT_WINDOW_MINUTES,
    now_epoch: float | None = None,
    runtime_logs_dir: Path | None = None,
    runtime_data_dir: Path | None = None,
    process_logs_dir: Path | None = None,
    suggestions_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    symbol_key = str(symbol or "").upper().strip()
    now_ts = _now_epoch(now_epoch)
    runtime_logs = Path(runtime_logs_dir or logs_dir())
    runtime_data = Path(runtime_data_dir or data_root())
    process_logs = Path(process_logs_dir or (repo_root() / "logs"))
    suggestions_file = Path(suggestions_path or canonical_suggestions_log_path())

    raw_sources: list[dict[str, Any]] = []
    notes: list[str] = []

    def _load_and_track(path: Path, label: str) -> Any:
        payload, meta = _read_json_file(path)
        meta["label"] = label
        raw_sources.append(meta)
        if meta.get("error"):
            notes.append(f"{label}: {meta['error']}")
        elif not meta.get("exists"):
            notes.append(f"{label}: missing")
        return payload

    suggestions_status = _load_and_track(runtime_logs / "suggestions_status.json", "suggestions_status") or {}
    engine_status = _load_and_track(runtime_logs / "engine_cycle_status.json", "engine_cycle_status") or {}
    feed_runtime = _load_and_track(runtime_logs / "feed_runtime_latest.json", "feed_runtime_latest") or {}
    freshness_latest = _load_and_track(runtime_logs / "freshness_latest.json", "freshness_latest") or {}
    token_resolution = _load_and_track(runtime_logs / "token_resolution.json", "token_resolution") or {}
    option_chain_latest = _load_and_track(runtime_data / "option_chain_latest.json", "option_chain_latest") or {}

    if suggestions_file.exists():
        raw_sources.append({"label": "suggestions_jsonl", "path": str(suggestions_file), "exists": True, "parse_ok": True, "missing": False, "error": None})
    else:
        raw_sources.append({"label": "suggestions_jsonl", "path": str(suggestions_file), "exists": False, "parse_ok": False, "missing": True, "error": None})
        notes.append("suggestions_jsonl: missing")

    advisory_rows_raw = _matching_advisory_rows(suggestions_file, symbol=symbol_key, trade_id=trade_id)
    advisory_rows: list[dict[str, Any]] = []
    advisory_errors: list[dict[str, Any]] = []
    for row in advisory_rows_raw:
        parsed, error = _deserialize_row_best_effort(row)
        advisory_rows.append(parsed)
        if error:
            advisory_errors.append({"trade_id": row.get("trade_id") or row.get("advisory_id"), "error": error})
    latest_row = advisory_rows[0] if advisory_rows else None
    previous_row = advisory_rows[1] if len(advisory_rows) > 1 else None
    latest_parse_error = advisory_errors[0]["error"] if advisory_errors else None

    advisory_section = _build_advisory_section(latest_row, parse_error=latest_parse_error)
    market_open_state = (
        suggestions_status.get("market_open")
        if "market_open" in suggestions_status
        else engine_status.get("market_open")
    )
    feed_debug_payload = dict(feed_runtime) if isinstance(feed_runtime, dict) else {}
    feed_health = _build_feed_health_section(feed_debug_payload, symbol=symbol_key, market_open=market_open_state)
    freshness_decision = _select_freshness_decision(
        freshness_latest if isinstance(freshness_latest, dict) else {},
        symbol=symbol_key,
        trade_id=trade_id,
    )
    freshness_section = _build_freshness_section(freshness_decision, advisory_section, market_open_state=market_open_state)
    blocker_state = _build_blocker_state_section(latest_row or {}, previous_row)
    chain_rows = _select_option_chain_rows(option_chain_latest, symbol=symbol_key, expiry=_norm_text(advisory_section.get("expiry")))
    option_chain_health = _build_option_chain_health_section(chain_rows, advisory_section)
    resolution_row = _select_token_resolution_row(token_resolution, symbol=symbol_key)
    resolution_meta = next((item for item in raw_sources if item.get("label") == "token_resolution"), {})
    resolution_epoch = None
    try:
        resolution_path = Path(str(resolution_meta.get("path") or ""))
        if resolution_path.exists():
            resolution_epoch = resolution_path.stat().st_mtime
    except Exception:
        resolution_epoch = None
    token_section = _build_token_resolution_section(resolution_row, advisory_section, resolution_epoch=resolution_epoch)
    log_snippets = _collect_log_snippets(
        symbol=symbol_key,
        trade_id=trade_id,
        window_minutes=minutes,
        now_epoch=now_ts,
        process_logs_dir=process_logs,
    )
    incident_summary = _incident_summary(
        advisory=advisory_section,
        feed_health=feed_health,
        freshness=freshness_section,
        blocker_state=blocker_state,
        suggestions_status=suggestions_status if isinstance(suggestions_status, dict) else {},
        engine_status=engine_status if isinstance(engine_status, dict) else {},
    )

    bundle = {
        "bundle_meta": {
            "generated_at": _iso_utc(now_ts),
            "epoch_now": now_ts,
            "symbol": symbol_key,
            "trade_id": _norm_text(trade_id),
            "window_minutes": int(minutes),
            "bundle_version": BUNDLE_VERSION,
        },
        "incident_summary": incident_summary,
        "feed_health": feed_health,
        "advisory": advisory_section,
        "freshness": freshness_section,
        "blocker_state": blocker_state,
        "option_chain_health": option_chain_health,
        "token_resolution": token_section,
        "log_snippets": log_snippets,
        "raw_sources": raw_sources,
        "notes": notes,
        "advisory_parse_errors": advisory_errors,
    }
    return bundle, raw_sources, log_snippets, advisory_rows_raw, {
        "suggestions_status": suggestions_status,
        "engine_cycle_status": engine_status,
        "feed_runtime_latest": feed_runtime,
        "freshness_latest": freshness_latest,
        "token_resolution": token_resolution,
        "option_chain_latest": option_chain_latest,
    }


def generate_incident_bundle(
    *,
    symbol: str,
    trade_id: str | None = None,
    minutes: int = DEFAULT_WINDOW_MINUTES,
    output_dir: str | Path | None = None,
    now_epoch: float | None = None,
    runtime_logs_dir: Path | None = None,
    runtime_data_dir: Path | None = None,
    process_logs_dir: Path | None = None,
    suggestions_path: Path | None = None,
) -> Path:
    now_ts = _now_epoch(now_epoch)
    symbol_key = str(symbol or "").upper().strip()
    base_dir = Path(output_dir or default_incident_output_dir()).expanduser()
    bundle_dir = base_dir / f"{datetime.fromtimestamp(now_ts).strftime('%Y%m%d_%H%M%S')}_{symbol_key}"
    raw_dir = bundle_dir / "raw"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    bundle, raw_sources, log_snippets, advisory_rows_raw, payloads = build_incident_bundle_payload(
        symbol=symbol_key,
        trade_id=trade_id,
        minutes=minutes,
        now_epoch=now_ts,
        runtime_logs_dir=runtime_logs_dir,
        runtime_data_dir=runtime_data_dir,
        process_logs_dir=process_logs_dir,
        suggestions_path=suggestions_path,
    )

    json_path = bundle_dir / "incident_bundle.json"
    txt_path = bundle_dir / "incident_bundle.txt"
    write_json_atomic(json_path, bundle)
    txt_path.write_text(_render_bundle_text(bundle), encoding="utf-8")

    runtime_logs = Path(runtime_logs_dir or logs_dir())
    runtime_data = Path(runtime_data_dir or data_root())
    suggestions_file = Path(suggestions_path or canonical_suggestions_log_path())
    for item in raw_sources:
        label = str(item.get("label") or "")
        path_text = _norm_text(item.get("path"))
        if not path_text:
            continue
        source_path = Path(path_text)
        if not source_path.exists():
            continue
        if source_path.suffix == ".json":
            _copy_raw_file(source_path, raw_dir)
    if suggestions_file.exists():
        _write_raw_json(raw_dir, "advisory_rows.json", advisory_rows_raw)
    _copy_log_snippets(raw_dir, log_snippets)

    for name, payload in payloads.items():
        if payload in (None, {}):
            continue
        if name == "option_chain_latest":
            _write_raw_json(raw_dir, "option_chain_latest.filtered.json", payload)
        elif name == "token_resolution":
            _write_raw_json(raw_dir, "token_resolution.filtered.json", payload)

    logger.info(
        "incident_bundle_generated path=%s symbol=%s trade_id=%s window_minutes=%s",
        bundle_dir,
        symbol_key,
        trade_id,
        minutes,
    )
    return bundle_dir
