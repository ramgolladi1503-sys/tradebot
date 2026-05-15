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
            # Session-tick gating skipped pruning for this symbol. The row may
            # still carry stale-count diagnostics from the attempted prune pass,
            # but no token was actually pruned from the final subscription.
            row["stale_option_pruned_count"] = 0
            row["stale_option_pruned_sample_tokens"] = []
            row["option_drop_reason"] = row.get("option_fail_reason")
        normalized.append(row)
    return normalized


def _normalize_prune_meta(
    *,
    retained: list[int],
    meta: dict[str, Any],
    option_rank_by_token: dict[int, tuple],
    token_to_symbol: dict[int, str],
    min_required_by_symbol: dict[str, int] | None,
) -> dict[str, Any]:
    out = dict(meta or {})
    if out.get("protected_stale_by_symbol"):
        return out
    pruned_by_symbol = dict(out.get("pruned_by_symbol") or {})
    if not pruned_by_symbol:
        return out
    minimums = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
    if not minimums:
        return out
    try:
        now = float(now_utc_epoch())
    except Exception:
        now = 0.0
    try:
        max_age = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
    except Exception:
        max_age = 2.5
    option_tokens = [int(t) for t in option_rank_by_token]
    try:
        rows = get_latest_tick_rows_db(option_tokens) or {}
    except Exception:
        rows = {}
    retained_set = {int(t) for t in list(retained or [])}
    protected: dict[str, int] = {}
    for symbol, minimum in minimums.items():
        if int(pruned_by_symbol.get(symbol, 0) or 0) <= 0 or minimum <= 0:
            continue
        retained_options = [
            int(token)
            for token in option_rank_by_token
            if int(token) in retained_set
            and str(token_to_symbol.get(int(token)) or "").upper() == symbol
        ]
        fresh_count = 0
        for token in retained_options:
            row = rows.get(int(token)) or rows.get(str(int(token))) or {}
            ts = _to_float(row.get("ts_epoch"), None)
            if ts is not None and now > 0 and (now - float(ts)) <= max_age:
                fresh_count += 1
        protected_count = max(0, min(int(minimum), len(retained_options)) - int(fresh_count))
        if protected_count:
            protected[symbol] = int(protected_count)
    if protected:
        out["protected_stale_by_symbol"] = protected
    return out


def _prune_stale_option_subscription_tokens(*, tokens, option_rank_by_token, token_to_symbol, min_required_by_symbol=None):  # noqa: F811
    _sync_contract_public_state()
    retained, meta = _contract_prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol=min_required_by_symbol,
    )
    _sync_contract_outputs()
    meta = _normalize_prune_meta(
        retained=list(retained or []),
        meta=dict(meta or {}),
        option_rank_by_token=dict(option_rank_by_token or {}),
        token_to_symbol=dict(token_to_symbol or {}),
        min_required_by_symbol=dict(min_required_by_symbol or {}),
    )
    return retained, meta


def build_depth_subscription_tokens(symbols=None, max_tokens=None):  # noqa: F811
    _sync_contract_public_state()
    tokens, resolution = _contract_build_depth_subscription_tokens(symbols, max_tokens=max_tokens)
    _sync_contract_outputs()
    return tokens, _normalize_depth_resolution_metadata(list(resolution or []))


_contracts.build_depth_subscription_tokens = build_depth_subscription_tokens
