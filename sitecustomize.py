"""Runtime compatibility shims loaded automatically by Python.

This project still has legacy replay tests and user workflows that pass
``freq="T"`` to ``pandas.date_range``. Newer pandas versions removed that
legacy minute alias and require ``"min"``. Keep the public runtime stable
without editing historical tests or replay fixtures.
"""

from __future__ import annotations

try:  # pragma: no cover - import-time compatibility shim
    import pandas as _pd
except Exception:  # pragma: no cover
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
