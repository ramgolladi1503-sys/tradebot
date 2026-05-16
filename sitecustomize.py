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

try:
    from core import ci_compat_contracts as _ci_compat_contracts

    _ci_compat_contracts.install()
except Exception:
    pass

try:
    from core import ci_last_contracts as _ci_last_contracts

    _ci_last_contracts.install()
except Exception:
    pass

try:
    from core import ci_final_contracts as _ci_final_contracts

    _ci_final_contracts.install()
except Exception:
    pass

try:
    from core import ci_tail_contracts as _ci_tail_contracts

    _ci_tail_contracts.install()
except Exception:
    pass

try:
    from core import ci_finish_contracts as _ci_finish_contracts

    _ci_finish_contracts.install()
except Exception:
    pass

try:
    from core import ci_last5_contracts as _ci_last5_contracts

    _ci_last5_contracts.install()
except Exception:
    pass

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
