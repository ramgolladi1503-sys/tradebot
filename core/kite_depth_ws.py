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
    tokens, resolution = _contract_build_depth_subscription_tokens(symbols, max_tokens=max_tokens)
    return tokens, _normalize_depth_resolution_metadata(list(resolution or []))


_contracts.build_depth_subscription_tokens = build_depth_subscription_tokens
