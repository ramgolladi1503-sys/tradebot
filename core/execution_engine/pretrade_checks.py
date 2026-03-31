from __future__ import annotations

from typing import Any, Tuple


_REQUIRED_INTENT_FIELDS = (
    "intent_id",
    "trade_id",
    "symbol",
    "direction",
    "entry_price",
    "stop_loss",
    "target",
    "qty",
    "final_action",
    "execution_status",
)


def _get(intent: Any, key: str, default=None):
    if isinstance(intent, dict):
        return intent.get(key, default)
    return getattr(intent, key, default)


def validate_execution_intent(intent: Any) -> Tuple[bool, str]:
    if not intent:
        return False, "no_intent"

    for field in _REQUIRED_INTENT_FIELDS:
        value = _get(intent, field)
        if value in (None, "", "None"):
            return False, f"missing_{field}"

    try:
        entry_price = float(_get(intent, "entry_price"))
        stop_loss = float(_get(intent, "stop_loss"))
        target = float(_get(intent, "target"))
        qty = int(_get(intent, "qty"))
    except Exception:
        return False, "invalid_numeric_fields"

    if entry_price <= 0:
        return False, "invalid_entry_price"
    if qty <= 0:
        return False, "invalid_qty"
    if stop_loss <= 0:
        return False, "invalid_stop_loss"
    if target <= 0:
        return False, "invalid_target"

    final_action = str(_get(intent, "final_action") or "").strip().upper()
    if final_action != "EXECUTE":
        return False, "final_action_not_execute"

    execution_status = str(_get(intent, "execution_status") or "").strip().lower()
    if execution_status != "executable":
        return False, "execution_status_not_executable"

    return True, "ok"
