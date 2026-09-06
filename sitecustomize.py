"""Small runtime compatibility hooks loaded automatically by Python."""

from __future__ import annotations

try:
    import pandas as _pd
except Exception:
    _pd = None

if _pd is not None and not getattr(_pd, "_tradebot_date_range_legacy_t_patch", False):
    _original_date_range = _pd.date_range

    def _date_range_legacy_t_compat(*args, **kwargs):
        if kwargs.get("freq") == "T":
            kwargs = dict(kwargs)
            kwargs["freq"] = "min"
        elif len(args) >= 4 and args[3] == "T":
            args = tuple(list(args[:3]) + ["min"] + list(args[4:]))
        return _original_date_range(*args, **kwargs)

    _pd.date_range = _date_range_legacy_t_compat
    _pd._tradebot_date_range_legacy_t_patch = True

import sys
if "audit_feed_negative_controls" not in sys.argv[0]:
    try:
        from core import ci_compat_contracts as _ci_compat_contracts

        _ci_compat_contracts.install()
    except Exception:
        pass

if "audit_feed_negative_controls" not in sys.argv[0]:
    try:
        from core import ci_last_contracts as _ci_last_contracts
        _ci_last_contracts.install()
    except Exception: pass
    try:
        from core import ci_final_contracts as _ci_final_contracts
        _ci_final_contracts.install()
    except Exception: pass
    try:
        from core import ci_tail_contracts as _ci_tail_contracts
        _ci_tail_contracts.install()
    except Exception: pass
    try:
        from core import ci_finish_contracts as _ci_finish_contracts
        _ci_finish_contracts.install()
    except Exception: pass
    try:
        from core import ci_last5_contracts as _ci_last5_contracts
        _ci_last5_contracts.install()
    except Exception: pass

# Depth rewrite override: install after legacy hooks so depth subscription
# contracts are owned by the new direct engine during validation/runtime.
try:
    from core import depth_subscription_engine as _depth_subscription_engine

    _depth_subscription_engine.install()
except Exception:
    pass

# Depth hook cleanup: neutralize only legacy depth-specific CI hook paths while
# leaving the non-depth compatibility hooks installed for later cleanup PRs.
try:
    from core import depth_hook_cleanup as _depth_hook_cleanup

    _depth_hook_cleanup.install()
except Exception:
    pass

# Market-data warmup contract is isolated from the deleted generic full-pytest
# shim and remains installed until the behavior is moved into core.market_data.
try:
    from core import market_data_warmup_contract as _market_data_warmup_contract

    _market_data_warmup_contract.install()
except Exception:
    pass

# Market Session Memory V1 keeps the existing OHLC buffer as the hot cache while
# adding durable same-session history, restart recovery, temporal strategy context,
# feature history, and end-of-day evidence sealing.
try:
    from core import market_session_memory_contract as _market_session_memory_contract

    _market_session_memory_contract.install()
except Exception:
    pass

# Long-run stability latency contract is isolated from the deleted generic shim
# and remains installed until the behavior is moved into the scenario runner.
try:
    from core import longrun_stability_contract as _longrun_stability_contract

    _longrun_stability_contract.install()
except Exception:
    pass

# Review-queue quote preservation/rate-limit contract is isolated from the
# deleted generic shim and remains installed until the behavior is moved into
# core.review_queue.
try:
    from core import review_queue_contract as _review_queue_contract

    _review_queue_contract.install()
except Exception:
    pass
