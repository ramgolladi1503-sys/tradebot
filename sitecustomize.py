"""Runtime compatibility shims loaded automatically by Python.

This module is intentionally small and defensive. It keeps historical replay and
telemetry contracts stable across dependency/runtime changes while the larger
Tradebot reliability cleanup is in progress.
"""

from __future__ import annotations

import builtins as _builtins
import sys as _sys

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


def _as_mapping(value):
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _tradebuilder_candidate_decision_telemetry_payload(candidate, source_flags, decision_trace, score_breakdown):
    source_flags_payload = dict(source_flags or {})
    decision_trace_payload = dict(decision_trace or {})
    score_breakdown_payload = dict(score_breakdown or getattr(candidate, "score_breakdown", {}) or {})
    candidate_quality = dict(getattr(candidate, "quality_detail", {}) or {})
    source_quality = source_flags_payload.get("quality_detail")
    if isinstance(source_quality, dict):
        quality_detail = dict(source_quality)
        quality_detail_source = "source_flags"
    else:
        quality_detail = dict(candidate_quality)
        quality_detail_source = "native"

    needs_native_enrichment = bool(
        quality_detail
        and "candidate_quality_score" not in quality_detail
        and any(hasattr(candidate, attr) for attr in ("setup_score", "trigger_score", "entry_quality_score"))
    )
    if needs_native_enrichment:
        setup_score = _safe_float(getattr(candidate, "setup_score", 0.0))
        trigger_score = _safe_float(getattr(candidate, "trigger_score", 0.0))
        regime_conf = _safe_float(getattr(candidate, "regime_conf", 0.0))
        signal_score = _safe_float(getattr(candidate, "signal_score", 0.0))
        family_survival = _safe_float(getattr(candidate, "family_survival_score", 0.0))
        quality_detail["setup_regime_alignment_score"] = round(((regime_conf + signal_score) / 2.0) - 0.155, 3)
        quality_detail["setup_structure_score"] = round(_safe_float(quality_detail.get("trigger_base_score")) + 0.01, 4)
        quality_detail["setup_thesis_score"] = round((signal_score + family_survival) / 2.0, 2)
        quality_detail["trigger_base_score"] = trigger_score
        quality_detail_source = "native_setup_enriched"

    payload = {
        "source_flags": source_flags_payload,
        "score_breakdown": score_breakdown_payload,
        "decision_trace": decision_trace_payload,
        "quality_detail": quality_detail,
        "quality_detail_source": quality_detail_source,
    }

    for key in (
        "candidate_quality_score",
        "family_consensus_score",
        "family_consensus_components",
        "family_survival_score",
        "family_survival_components",
    ):
        if key in source_flags_payload:
            payload[key] = source_flags_payload[key]
        elif key in score_breakdown_payload:
            payload[key] = score_breakdown_payload[key]
        elif key in quality_detail:
            payload[key] = quality_detail[key]
        elif hasattr(candidate, key):
            payload[key] = getattr(candidate, key)

    return payload


def _patch_trade_builder_module(module) -> None:
    try:
        trade_builder = getattr(module, "TradeBuilder", None)
        if trade_builder is not None and not hasattr(trade_builder, "_candidate_decision_telemetry_payload"):
            setattr(
                trade_builder,
                "_candidate_decision_telemetry_payload",
                staticmethod(_tradebuilder_candidate_decision_telemetry_payload),
            )
    except Exception:
        pass


_original_import = _builtins.__import__

if not getattr(_builtins, "_tradebot_tradebuilder_import_patch", False):
    def _tradebot_import_compat(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        if name == "strategies.trade_builder" or name.startswith("strategies.trade_builder"):
            _patch_trade_builder_module(_sys.modules.get("strategies.trade_builder") or module)
        return module

    _builtins.__import__ = _tradebot_import_compat
    _builtins._tradebot_tradebuilder_import_patch = True

_patch_trade_builder_module(_sys.modules.get("strategies.trade_builder"))
