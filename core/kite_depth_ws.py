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


def _sync_contract_public_state() -> None:
    """Mirror monkeypatch-sensitive public globals into the contract module.

    Legacy tests patch symbols on ``core.kite_depth_ws`` directly. The migrated
    implementation executes in the private contract module, so those patches
    must be copied across before dispatch.
    """
    for name in (
        "_underlying_ltp",
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


def build_depth_subscription_tokens(symbols=None, max_tokens=None):  # noqa: F811
    _sync_contract_public_state()
    tokens, resolution = _contract_build_depth_subscription_tokens(symbols, max_tokens=max_tokens)
    _sync_contract_outputs()
    return tokens, _normalize_depth_resolution_metadata(list(resolution or []))


_contracts.build_depth_subscription_tokens = build_depth_subscription_tokens
