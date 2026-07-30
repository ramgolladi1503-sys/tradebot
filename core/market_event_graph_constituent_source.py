"""Live, read-only NIFTY constituent source for the frozen market-event graph.

The source resolves a frozen current constituent manifest to NSE instrument tokens,
requests read-only WebSocket subscriptions, reconstructs completed one-minute returns
from the canonical tick database, and attaches the exact producer input contract.
It never creates an order, changes a strategy threshold, or fabricates missing bars.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, time as wall_time
from pathlib import Path
from typing import Any

from core.events import write_json_atomic
from core.market_event_graph_breadth_producer import (
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)
from core.market_event_graph_tick_reader import MINUTE_SECONDS, read_last_ticks_by_minute
from core.paths import repo_root, runtime_dir
from core.time_utils import IST_TZ

SOURCE_SCHEMA_VERSION = 1
DEFAULT_MANIFEST_PATH = (
    repo_root() / "config" / "market_event_graph_nifty50_constituents_20260605.json"
)
DEFAULT_STATE_PATH = runtime_dir() / "market_event_graph" / "constituent_source_state.json"
DEFAULT_MIN_CONSTITUENTS = 40
DEFAULT_BACKFILL_MINUTES = 16
DEFAULT_COMPLETION_GRACE_SEC = 5.0
MAX_CATCHUP_MINUTES = 120

InstrumentProvider = Callable[[], Sequence[Mapping[str, Any]]]
SubscriptionFunction = Callable[[list[int]], bool]
TickReader = Callable[[Iterable[int], Iterable[float]], dict[int, dict[int, dict[str, Any]]]]

_STATE_LOCK = threading.RLock()


def attach_market_event_graph_constituent_source(
    metadata: Mapping[str, Any] | None,
    *,
    symbol: str,
    as_of_epoch: float | None,
    enabled: bool | None = None,
    manifest_path: str | Path | None = None,
    state_path: str | Path | None = None,
    instrument_provider: InstrumentProvider | None = None,
    subscription_fn: SubscriptionFunction | None = None,
    tick_reader: TickReader | None = None,
    index_token: int | None = None,
) -> dict[str, Any]:
    """Attach completed constituent-return bars and frozen runtime provenance.

    Existing explicit ``completed_constituent_bars`` are preserved. This keeps
    replay/test callers authoritative and prevents live-source data from replacing
    independently supplied evidence.
    """

    out = dict(metadata or {})
    out.setdefault("market_event_graph_constituent_source_status", "NOT_EVALUATED")
    out.setdefault("market_event_graph_constituent_source_reason", "not_evaluated")
    out.setdefault("market_event_graph_constituent_source_managed", False)

    if str(symbol or "").strip().upper() != "NIFTY":
        return _with_status(out, "NOT_APPLICABLE", "symbol_not_nifty")
    if isinstance(out.get("completed_constituent_bars"), Sequence) and not isinstance(
        out.get("completed_constituent_bars"), (str, bytes)
    ):
        return _with_status(out, "EXTERNAL_INPUT_PRESERVED", "caller_supplied_completed_bars")
    if not _source_enabled(out, enabled):
        return _with_status(out, "DISABLED", "market_event_graph_live_source_disabled")

    try:
        now_epoch = float(as_of_epoch)
    except (TypeError, ValueError):
        return _with_status(out, "INVALID_CONTEXT_TIME", "as_of_epoch_missing_or_invalid")
    if not math.isfinite(now_epoch) or now_epoch <= 0.0:
        return _with_status(out, "INVALID_CONTEXT_TIME", "as_of_epoch_missing_or_invalid")

    manifest_file = Path(manifest_path or DEFAULT_MANIFEST_PATH).expanduser().resolve()
    manifest, manifest_sha, manifest_error = _load_manifest(manifest_file)
    if manifest is None:
        return _with_status(out, "MANIFEST_INVALID", manifest_error)

    session_date = datetime.fromtimestamp(now_epoch, tz=IST_TZ).date().isoformat()
    source_state_path = Path(state_path or DEFAULT_STATE_PATH).expanduser().resolve()

    with _STATE_LOCK:
        state = _load_state(
            source_state_path,
            session_date=session_date,
            manifest_sha256=manifest_sha,
        )

        token_resolution = _state_token_resolution(state)
        if token_resolution is None:
            rows = _instrument_rows(instrument_provider)
            token_resolution = resolve_constituent_tokens(
                manifest,
                rows,
                index_token=index_token,
            )
            if token_resolution["status"] != "READY":
                out.update(
                    {
                        "market_event_graph_constituent_source_evidence": token_resolution,
                        "market_event_graph_constituent_manifest_sha256": manifest_sha,
                    }
                )
                return _with_status(out, "TOKEN_RESOLUTION_FAILED", token_resolution["reason"])
            state["token_resolution"] = token_resolution

        constituent_tokens = {
            str(name): int(token)
            for name, token in dict(token_resolution["constituent_tokens"]).items()
        }
        resolved_index_token = int(token_resolution["index_token"])
        all_tokens = sorted({resolved_index_token, *constituent_tokens.values()})

        subscribed = _subscribe(all_tokens, subscription_fn)
        state["subscription"] = {
            "requested_token_count": len(all_tokens),
            "subscription_ok": bool(subscribed),
            "is_order_action": False,
            "broker_api_called": False,
        }

        latest_completed_end = _latest_completed_minute_end(now_epoch)
        session_first_end, session_last_end = _session_bounds(now_epoch)
        if latest_completed_end < session_first_end:
            evidence = _source_evidence(
                state,
                manifest=manifest,
                manifest_sha256=manifest_sha,
                latest_completed_end=latest_completed_end,
                subscribed=subscribed,
            )
            out["market_event_graph_constituent_source_evidence"] = evidence
            return _with_status(out, "BEFORE_SESSION", "no_completed_regular_session_minute")
        latest_completed_end = min(latest_completed_end, session_last_end)

        bars = _valid_cached_bars(state.get("bars"), session_date=session_date)
        start_end = _next_boundary(
            bars,
            latest_completed_end=latest_completed_end,
            session_first_end=session_first_end,
        )
        target_ends = _target_boundaries(start_end, latest_completed_end)
        build_failures: list[dict[str, Any]] = []

        if target_ends:
            boundaries = sorted({end for target in target_ends for end in (target - 60, target)})
            reader = tick_reader or _default_tick_reader
            try:
                ticks_by_minute = reader(all_tokens, boundaries)
            except Exception as exc:
                ticks_by_minute = {}
                build_failures.append(
                    {
                        "minute_end_epoch": target_ends[0],
                        "reason": f"tick_reader_error:{exc.__class__.__name__}",
                    }
                )

            if not build_failures:
                for minute_end in target_ends:
                    row, failure = _build_completed_return_row(
                        minute_end,
                        session_date=session_date,
                        index_token=resolved_index_token,
                        constituent_tokens=constituent_tokens,
                        ticks_by_minute=ticks_by_minute,
                        manifest_sha256=manifest_sha,
                    )
                    if row is None:
                        build_failures.append(failure)
                        break
                    if bars and float(row["source_bar_end_epoch"]) != float(
                        bars[-1]["source_bar_end_epoch"]
                    ) + MINUTE_SECONDS:
                        build_failures.append(
                            {
                                "minute_end_epoch": minute_end,
                                "reason": "non_consecutive_source_boundary",
                            }
                        )
                        break
                    bars.append(row)

        state["bars"] = bars
        state["last_refresh_epoch"] = now_epoch
        state["last_completed_boundary_epoch"] = latest_completed_end
        state["last_build_failures"] = build_failures
        state["manifest"] = {
            "path": str(manifest_file),
            "sha256": manifest_sha,
            "effective_from": manifest["effective_from"],
            "retrieved_on": manifest["retrieved_on"],
            "source_url": manifest["source_url"],
        }
        _write_state(source_state_path, state)

        evidence = _source_evidence(
            state,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            latest_completed_end=latest_completed_end,
            subscribed=subscribed,
        )
        out.update(frozen_threshold_metadata())
        out["market_event_graph_runtime_state"] = state["runtime_state"]
        out["completed_constituent_bars"] = list(bars)
        out["market_event_graph_constituent_manifest_sha256"] = manifest_sha
        out["market_event_graph_constituent_source_evidence"] = evidence
        out["market_event_graph_constituent_source_state_path"] = str(source_state_path)
        out["market_event_graph_constituent_source_managed"] = True

        if build_failures:
            return _with_status(out, "INTERVAL_GAP_BLOCKED", build_failures[0]["reason"])
        if not bars:
            return _with_status(out, "NO_COMPLETED_BARS", "tick_rows_not_available")
        if int(bars[-1]["source_bar_end_epoch"]) < int(latest_completed_end):
            return _with_status(out, "CATCHUP_PENDING", "completed_history_not_current")
        if len(bars) < 4:
            return _with_status(out, "PARTIAL_HISTORY", "fewer_than_four_completed_intervals")
        if not subscribed:
            return _with_status(out, "READY_SUBSCRIPTION_UNCONFIRMED", "ws_subscription_not_confirmed")
        return _with_status(out, "READY", "completed_constituent_bars_current")


def persist_market_event_graph_constituent_state(metadata: Mapping[str, Any] | None) -> bool:
    """Persist caller-owned graph state after the advisory generator mutates it."""

    if not isinstance(metadata, Mapping) or metadata.get(
        "market_event_graph_constituent_source_managed"
    ) is not True:
        return False
    raw_path = str(metadata.get("market_event_graph_constituent_source_state_path") or "").strip()
    runtime_state = metadata.get("market_event_graph_runtime_state")
    bars = metadata.get("completed_constituent_bars")
    manifest_sha = str(metadata.get("market_event_graph_constituent_manifest_sha256") or "")
    if not raw_path or not isinstance(runtime_state, dict) or not isinstance(bars, list):
        return False

    path = Path(raw_path).expanduser().resolve()
    with _STATE_LOCK:
        state = _read_json(path)
        if not isinstance(state, dict) or int(state.get("schema_version", -1)) != SOURCE_SCHEMA_VERSION:
            return False
        if str(state.get("manifest_sha256") or "") != manifest_sha:
            return False
        state["runtime_state"] = dict(runtime_state)
        state["bars"] = list(bars)
        _write_state(path, state)
    return True


def resolve_constituent_tokens(
    manifest: Mapping[str, Any],
    instruments: Sequence[Mapping[str, Any]],
    *,
    index_token: int | None = None,
) -> dict[str, Any]:
    """Resolve exactly one NSE EQ token per frozen constituent symbol."""

    expected = tuple(str(value).strip().upper() for value in manifest.get("constituents", ()))
    candidates: dict[str, list[int]] = {symbol: [] for symbol in expected}
    index_candidates: list[int] = []
    index_tradingsymbol = str(manifest.get("index_tradingsymbol") or "NIFTY 50").upper()

    for raw in instruments:
        if not isinstance(raw, Mapping):
            continue
        exchange = str(raw.get("exchange") or "").upper()
        tradingsymbol = str(raw.get("tradingsymbol") or "").strip().upper()
        instrument_type = str(raw.get("instrument_type") or "").strip().upper()
        try:
            token = int(raw.get("instrument_token"))
        except (TypeError, ValueError):
            continue
        if token <= 0 or exchange != "NSE":
            continue
        if tradingsymbol in candidates and instrument_type in {"EQ", "EQUITY"}:
            candidates[tradingsymbol].append(token)
        if tradingsymbol == index_tradingsymbol and instrument_type in {"INDEX", "INDICES"}:
            index_candidates.append(token)

    missing = sorted(symbol for symbol, values in candidates.items() if not values)
    ambiguous = sorted(symbol for symbol, values in candidates.items() if len(set(values)) != 1)
    resolved = {
        symbol: sorted(set(values))[0]
        for symbol, values in candidates.items()
        if len(set(values)) == 1
    }

    resolved_index = None
    if index_token is not None:
        try:
            parsed_index = int(index_token)
        except (TypeError, ValueError):
            parsed_index = 0
        if parsed_index > 0:
            resolved_index = parsed_index
    if resolved_index is None and len(set(index_candidates)) == 1:
        resolved_index = sorted(set(index_candidates))[0]

    if missing or ambiguous or resolved_index is None:
        return {
            "status": "FAILED",
            "reason": "instrument_tokens_missing_or_ambiguous",
            "expected_constituent_count": len(expected),
            "resolved_constituent_count": len(resolved),
            "missing_symbols": missing,
            "ambiguous_symbols": ambiguous,
            "index_token_resolved": resolved_index is not None,
            "constituent_tokens": resolved,
            "index_token": resolved_index,
        }
    return {
        "status": "READY",
        "reason": "all_manifest_tokens_resolved",
        "expected_constituent_count": len(expected),
        "resolved_constituent_count": len(resolved),
        "missing_symbols": [],
        "ambiguous_symbols": [],
        "index_token_resolved": True,
        "constituent_tokens": resolved,
        "index_token": int(resolved_index),
    }


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, str, str]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None, "", "manifest_not_readable"
    try:
        schema = int(payload.get("schema_version", -1))
    except (TypeError, ValueError):
        schema = -1
    symbols = [str(value).strip().upper() for value in payload.get("constituents", ())]
    if schema != 1:
        return None, "", "manifest_schema_invalid"
    if payload.get("index_symbol") != "NIFTY" or payload.get("exchange") != "NSE":
        return None, "", "manifest_index_contract_invalid"
    if len(symbols) != 50 or len(set(symbols)) != 50 or any(not symbol for symbol in symbols):
        return None, "", "manifest_requires_exactly_50_unique_symbols"
    if payload.get("historical_backfill_allowed") is not False:
        return None, "", "manifest_historical_backfill_must_be_false"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return payload, hashlib.sha256(canonical.encode("utf-8")).hexdigest(), ""


def _load_state(path: Path, *, session_date: str, manifest_sha256: str) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return _new_state(session_date, manifest_sha256)
    if int(payload.get("schema_version", -1)) != SOURCE_SCHEMA_VERSION:
        return _new_state(session_date, manifest_sha256)
    if str(payload.get("session_date") or "") != session_date:
        return _new_state(session_date, manifest_sha256)
    if str(payload.get("manifest_sha256") or "") != manifest_sha256:
        return _new_state(session_date, manifest_sha256)
    runtime_state = payload.get("runtime_state")
    if not isinstance(runtime_state, dict) or str(runtime_state.get("session_date") or "") != session_date:
        payload["runtime_state"] = initial_market_event_graph_runtime_state(session_date)
    return payload


def _new_state(session_date: str, manifest_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "session_date": session_date,
        "manifest_sha256": manifest_sha256,
        "runtime_state": initial_market_event_graph_runtime_state(session_date),
        "bars": [],
        "token_resolution": None,
        "subscription": {},
        "last_build_failures": [],
    }


def _state_token_resolution(state: Mapping[str, Any]) -> dict[str, Any] | None:
    value = state.get("token_resolution")
    if not isinstance(value, dict) or value.get("status") != "READY":
        return None
    tokens = value.get("constituent_tokens")
    if not isinstance(tokens, dict) or len(tokens) != 50:
        return None
    try:
        if int(value.get("index_token")) <= 0:
            return None
        if any(int(token) <= 0 for token in tokens.values()):
            return None
    except (TypeError, ValueError):
        return None
    return value


def _instrument_rows(provider: InstrumentProvider | None) -> Sequence[Mapping[str, Any]]:
    if provider is not None:
        try:
            rows = provider()
        except Exception:
            return ()
        return rows if isinstance(rows, Sequence) else ()
    try:
        from core.kite_client import kite_client

        rows = kite_client.instruments("NSE")
    except Exception:
        return ()
    return rows if isinstance(rows, Sequence) else ()


def _subscribe(tokens: list[int], function: SubscriptionFunction | None) -> bool:
    if function is not None:
        try:
            return bool(function(tokens))
        except Exception:
            return False
    try:
        from core.kite_depth_ws import ensure_subscribed_tokens

        return bool(
            ensure_subscribed_tokens(
                tokens,
                reason="market_event_graph_constituent_breadth",
                symbol=None,
            )
        )
    except Exception:
        return False


def _default_tick_reader(
    tokens: Iterable[int],
    boundaries: Iterable[float],
) -> dict[int, dict[int, dict[str, Any]]]:
    return read_last_ticks_by_minute(tokens, boundaries)


def _latest_completed_minute_end(now_epoch: float) -> int:
    grace = _float_env(
        "MARKET_EVENT_GRAPH_SOURCE_COMPLETION_GRACE_SEC",
        DEFAULT_COMPLETION_GRACE_SEC,
        minimum=0.0,
        maximum=30.0,
    )
    return int(math.floor((float(now_epoch) - grace) / MINUTE_SECONDS) * MINUTE_SECONDS)


def _session_bounds(now_epoch: float) -> tuple[int, int]:
    local = datetime.fromtimestamp(now_epoch, tz=IST_TZ)
    open_dt = datetime.combine(local.date(), wall_time(9, 15), tzinfo=IST_TZ)
    close_dt = datetime.combine(local.date(), wall_time(15, 30), tzinfo=IST_TZ)
    return int(open_dt.timestamp()) + MINUTE_SECONDS, int(close_dt.timestamp())


def _next_boundary(
    bars: Sequence[Mapping[str, Any]],
    *,
    latest_completed_end: int,
    session_first_end: int,
) -> int:
    if bars:
        return int(float(bars[-1]["source_bar_end_epoch"])) + MINUTE_SECONDS
    backfill = _int_env(
        "MARKET_EVENT_GRAPH_SOURCE_BACKFILL_MINUTES",
        DEFAULT_BACKFILL_MINUTES,
        minimum=4,
        maximum=MAX_CATCHUP_MINUTES,
    )
    return max(session_first_end, latest_completed_end - ((backfill - 1) * MINUTE_SECONDS))


def _target_boundaries(start_end: int, latest_completed_end: int) -> list[int]:
    if start_end > latest_completed_end:
        return []
    values = list(range(start_end, latest_completed_end + 1, MINUTE_SECONDS))
    return values[:MAX_CATCHUP_MINUTES]


def _build_completed_return_row(
    minute_end: int,
    *,
    session_date: str,
    index_token: int,
    constituent_tokens: Mapping[str, int],
    ticks_by_minute: Mapping[int, Mapping[int, Mapping[str, Any]]],
    manifest_sha256: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    previous_end = minute_end - MINUTE_SECONDS
    current_ticks = ticks_by_minute.get(minute_end, {})
    previous_ticks = ticks_by_minute.get(previous_end, {})
    index_current = current_ticks.get(index_token)
    index_previous = previous_ticks.get(index_token)
    if not _valid_tick(index_current) or not _valid_tick(index_previous):
        return None, {
            "minute_end_epoch": minute_end,
            "reason": "index_tick_pair_missing",
        }

    index_ret1 = (float(index_current["ltp"]) / float(index_previous["ltp"])) - 1.0
    returns_by_symbol: dict[str, float] = {}
    missing_symbols: list[str] = []
    for symbol, token in sorted(constituent_tokens.items()):
        current = current_ticks.get(int(token))
        previous = previous_ticks.get(int(token))
        if not _valid_tick(current) or not _valid_tick(previous):
            missing_symbols.append(symbol)
            continue
        value = (float(current["ltp"]) / float(previous["ltp"])) - 1.0
        if not math.isfinite(value):
            missing_symbols.append(symbol)
            continue
        returns_by_symbol[symbol] = value

    if len(returns_by_symbol) < DEFAULT_MIN_CONSTITUENTS:
        return None, {
            "minute_end_epoch": minute_end,
            "reason": "constituent_tick_pair_coverage_below_minimum",
            "participation_count": len(returns_by_symbol),
            "missing_count": len(missing_symbols),
            "missing_symbols": missing_symbols,
        }

    return (
        {
            "ts_epoch": float(minute_end),
            "source_bar_end_epoch": float(minute_end),
            "session_date": session_date,
            "index_ret1": index_ret1,
            "constituent_ret1": [returns_by_symbol[symbol] for symbol in sorted(returns_by_symbol)],
            "constituent_ret1_by_symbol": returns_by_symbol,
            "participation_count": len(returns_by_symbol),
            "missing_constituent_count": len(missing_symbols),
            "missing_constituent_symbols": missing_symbols,
            "manifest_sha256": manifest_sha256,
            "completed": True,
            "source": "live_tick_store_completed_minute",
            "allowed_for_live_execution": False,
            "is_order_action": False,
            "broker_api_called": False,
        },
        {},
    )


def _valid_tick(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        price = float(value.get("ltp"))
        timestamp = float(value.get("ts_epoch"))
    except (TypeError, ValueError):
        return False
    return price > 0.0 and math.isfinite(price) and math.isfinite(timestamp)


def _valid_cached_bars(value: Any, *, session_date: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    prior_end: float | None = None
    for raw in value:
        if not isinstance(raw, dict) or str(raw.get("session_date") or "") != session_date:
            return []
        try:
            source_end = float(raw["source_bar_end_epoch"])
            ts_epoch = float(raw["ts_epoch"])
            participation = int(raw["participation_count"])
        except (KeyError, TypeError, ValueError):
            return []
        if source_end != ts_epoch or participation < DEFAULT_MIN_CONSTITUENTS:
            return []
        if prior_end is not None and source_end != prior_end + MINUTE_SECONDS:
            return []
        output.append(dict(raw))
        prior_end = source_end
    return output


def _source_evidence(
    state: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    latest_completed_end: int,
    subscribed: bool,
) -> dict[str, Any]:
    bars = state.get("bars") if isinstance(state.get("bars"), list) else []
    latest_bar_end = bars[-1].get("source_bar_end_epoch") if bars else None
    latest_participation = bars[-1].get("participation_count") if bars else 0
    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "session_date": state.get("session_date"),
        "manifest_sha256": manifest_sha256,
        "manifest_effective_from": manifest.get("effective_from"),
        "manifest_retrieved_on": manifest.get("retrieved_on"),
        "manifest_status": manifest.get("manifest_status"),
        "expected_constituent_count": len(manifest.get("constituents", ())),
        "resolved_constituent_count": int(
            (state.get("token_resolution") or {}).get("resolved_constituent_count", 0)
        ),
        "subscription_ok": bool(subscribed),
        "completed_bar_count": len(bars),
        "latest_completed_boundary_epoch": latest_completed_end,
        "latest_bar_end_epoch": latest_bar_end,
        "latest_participation_count": latest_participation,
        "last_build_failures": list(state.get("last_build_failures") or []),
        "source": "live_tick_store_completed_minute",
        "historical_backfill_allowed": False,
        "allowed_for_live_execution": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


def _with_status(payload: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    payload["market_event_graph_constituent_source_status"] = str(status)
    payload["market_event_graph_constituent_source_reason"] = str(reason)
    return payload


def _source_enabled(metadata: Mapping[str, Any], explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    if "market_event_graph_live_source_enable" in metadata:
        return bool(metadata.get("market_event_graph_live_source_enable"))
    return str(os.getenv("MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    write_json_atomic(path, dict(state))


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return max(minimum, min(maximum, value))


__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "DEFAULT_STATE_PATH",
    "SOURCE_SCHEMA_VERSION",
    "attach_market_event_graph_constituent_source",
    "persist_market_event_graph_constituent_state",
    "resolve_constituent_tokens",
]
