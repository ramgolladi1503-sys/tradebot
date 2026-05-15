"""Depth websocket public module with migrated subscription contracts.

The migrated depth-contract implementation is kept in a private base module so
this public module can own final public metadata normalization without reviving
import-time CI compatibility hooks.
"""

from __future__ import annotations

from typing import Any

from core import _kite_depth_ws_contracts_base as _contracts

for _name, _value in vars(_contracts).items():
    if _name in {"__name__", "__package__", "__loader__", "__spec__", "__file__", "__cached__"}:
        continue
    globals()[_name] = _value

_contract_build_depth_subscription_tokens = _contracts.build_depth_subscription_tokens
_contract_prune_stale_option_subscription_tokens = _contracts._prune_stale_option_subscription_tokens


def _sync_contract_public_state() -> None:
    """Mirror monkeypatch-sensitive public globals into the contract module.

    Legacy tests patch symbols on ``core.kite_depth_ws`` directly. The migrated
    implementation executes in the private contract module, so those patches
    must be copied across before dispatch.
    """
    for name in (
        "_underlying_ltp",
        "_maybe_raise_option_token_incident",
        "get_sticky_tokens",
        "get_latest_tick_rows_db",
        "now_utc_epoch",
        "kite_client",
        "cfg",
        "_DEPTH_WS_START_EPOCH",
        "_SYMBOL_LAST_OPTION_TICK_TS",
        "_STALE_PRUNE_STRIKES_BY_TOKEN",
        "_LAST_ATM_BY_SYMBOL",
        "_LAST_OPTION_COUNTS_BY_SYMBOL",
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL",
        "_LAST_DESIRED_TOKENS",
    ):
        if name in globals():
            setattr(_contracts, name, globals()[name])


def _sync_contract_outputs() -> None:
    for name in (
        "_UNDERLYING_TOKENS",
        "_UNDERLYING_TOKEN_TO_SYMBOL",
        "_TOKEN_TO_SYMBOL",
        "_LAST_OPTION_COUNTS_BY_SYMBOL",
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL",
        "_LAST_DESIRED_TOKENS",
        "_DEPTH_WS_START_EPOCH",
        "_STALE_PRUNE_STRIKES_BY_TOKEN",
        "_LAST_ATM_BY_SYMBOL",
    ):
        if hasattr(_contracts, name):
            globals()[name] = getattr(_contracts, name)


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _dedupe_ints(values: Any) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in list(values or []):
        try:
            token = int(value)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _session_tick_skipped_count(row: dict[str, Any], symbol: str) -> int:
    skipped = row.get("stale_option_session_tick_skipped_count_by_symbol") or {}
    try:
        return int(dict(skipped).get(str(symbol or "").upper(), 0) or 0)
    except Exception:
        return 0


def _normalize_depth_resolution_metadata(resolution: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in list(resolution or []):
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        row = dict(item)
        symbol = str(row.get("symbol") or "").upper()
        if _session_tick_skipped_count(row, symbol) > 0:
            row["stale_option_pruned_count"] = 0
            row["stale_option_pruned_sample_tokens"] = []
            row["option_drop_reason"] = row.get("option_fail_reason")
        normalized.append(row)
    return normalized


def _final_pruned_by_symbol(*, original_tokens: list[int], retained: list[int], option_rank_by_token: dict[int, tuple], token_to_symbol: dict[int, str]) -> dict[str, int]:
    original_set = {int(t) for t in _dedupe_ints(original_tokens) if int(t) in option_rank_by_token}
    retained_set = {int(t) for t in _dedupe_ints(retained) if int(t) in option_rank_by_token}
    out: dict[str, int] = {}
    for token in sorted(original_set - retained_set):
        symbol = str(token_to_symbol.get(int(token)) or "").upper()
        if symbol:
            out[symbol] = out.get(symbol, 0) + 1
    return out


def _direct_prune_contract(
    *,
    tokens: list[int],
    option_rank_by_token: dict[int, tuple],
    token_to_symbol: dict[int, str],
    min_required_by_symbol: dict[str, int] | None,
    meta: dict[str, Any] | None = None,
) -> tuple[list[int], dict[str, Any]]:
    token_list = _dedupe_ints(tokens)
    option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
    token_symbol = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
    minimums = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
    out_meta = dict(meta or {})
    if not option_rank or not minimums:
        return token_list, out_meta

    try:
        enabled = bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True))
    except Exception:
        enabled = True
    if not enabled:
        out_meta.setdefault("enabled", False)
        return token_list, out_meta

    try:
        now = float(now_utc_epoch())
    except Exception:
        now = 0.0
    try:
        max_age = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
    except Exception:
        max_age = 2.5
    try:
        require_session = bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True))
    except Exception:
        require_session = True
    session_symbols = {str(k).upper() for k in dict(globals().get("_SYMBOL_LAST_OPTION_TICK_TS") or {}).keys()}
    option_tokens = [int(t) for t in token_list if int(t) in option_rank]
    try:
        rows = get_latest_tick_rows_db(option_tokens) or {}
    except Exception:
        rows = {}

    non_options = [int(t) for t in token_list if int(t) not in option_rank]
    retained = list(non_options)
    protected_stale_by_symbol: dict[str, int] = {}
    skipped_by_symbol: dict[str, int] = {}
    stale_samples: list[dict[str, object]] = []

    symbols = sorted({token_symbol.get(int(t), "") for t in option_tokens if token_symbol.get(int(t), "")})
    for symbol in symbols:
        sym_options = [int(t) for t in option_tokens if token_symbol.get(int(t)) == symbol]
        if require_session and symbol not in session_symbols:
            retained.extend(sym_options)
            skipped_by_symbol[symbol] = len(sym_options)
            continue
        fresh: list[int] = []
        stale: list[int] = []
        for token in sym_options:
            row = rows.get(int(token)) or rows.get(str(int(token))) or {}
            ts = _to_float(row.get("ts_epoch"), None)
            if ts is not None and now > 0 and (now - float(ts)) <= max_age:
                fresh.append(int(token))
            else:
                stale.append(int(token))
        minimum = max(0, int(minimums.get(symbol, 0) or 0))
        protected_needed = max(0, minimum - len(fresh))
        stale_sorted = sorted(stale, key=lambda token: option_rank.get(int(token), (float("inf"), 2, float("inf"), 2, int(token))), reverse=True)
        protected = stale_sorted[:protected_needed]
        retained.extend(fresh + protected)
        if protected:
            protected_stale_by_symbol[symbol] = len(protected)

    retained = _dedupe_ints(retained)
    pruned_by_symbol = _final_pruned_by_symbol(
        original_tokens=token_list,
        retained=retained,
        option_rank_by_token=option_rank,
        token_to_symbol=token_symbol,
    )
    for symbol, count in pruned_by_symbol.items():
        missing = [
            int(token)
            for token in option_tokens
            if token_symbol.get(int(token)) == symbol and int(token) not in set(retained)
        ]
        for token in missing[:10]:
            stale_samples.append({"token": int(token), "symbol": symbol})
    out_meta.update(
        {
            "enabled": True,
            "max_age_sec": max_age,
            "require_session_tick": require_session,
            "min_required_by_symbol": minimums,
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": protected_stale_by_symbol,
            "pruned_count": sum(pruned_by_symbol.values()),
            "kept_count": len(retained),
            "pruned_by_symbol": pruned_by_symbol,
            "session_tick_skipped_by_symbol": skipped_by_symbol,
            "stale_option_session_tick_skipped_count_by_symbol": skipped_by_symbol,
            "stale_samples": stale_samples[:10],
        }
    )
    return retained, out_meta


def _prune_stale_option_subscription_tokens(*, tokens, option_rank_by_token, token_to_symbol, min_required_by_symbol=None):  # noqa: F811
    _sync_contract_public_state()
    _, meta = _contract_prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol=min_required_by_symbol,
    )
    _sync_contract_outputs()
    return _direct_prune_contract(
        tokens=list(tokens or []),
        option_rank_by_token=dict(option_rank_by_token or {}),
        token_to_symbol=dict(token_to_symbol or {}),
        min_required_by_symbol=dict(min_required_by_symbol or {}),
        meta=dict(meta or {}),
    )


def build_depth_subscription_tokens(symbols=None, max_tokens=None):  # noqa: F811
    _sync_contract_public_state()
    tokens, resolution = _contract_build_depth_subscription_tokens(symbols, max_tokens=max_tokens)
    _sync_contract_outputs()
    return tokens, _normalize_depth_resolution_metadata(list(resolution or []))


_contracts.build_depth_subscription_tokens = build_depth_subscription_tokens
