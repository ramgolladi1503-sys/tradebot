from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .option_repricing_lag_math import RepricingLagError

_REQUIRED_FUTURES = (
    "local_ts",
    "instrument_token",
    "last_price",
    "best_bid",
    "best_ask",
    "depth_json",
    "volume",
)
_REQUIRED_OPTIONS = _REQUIRED_FUTURES
_REQUIRED_MASTER = (
    "instrument_token",
    "tradingsymbol",
    "name",
    "expiry",
    "strike",
    "instrument_type",
    "segment",
    "exchange",
    "lot_size",
)


def _missing_columns(
    frame: pd.DataFrame | None, required: tuple[str, ...]
) -> list[str]:
    if frame is None:
        return list(required)
    return sorted(set(required) - set(frame.columns))


def _valid_quote_rate(frame: pd.DataFrame | None) -> float:
    if frame is None or frame.empty:
        return 0.0
    bid = pd.to_numeric(frame["best_bid"], errors="coerce")
    ask = pd.to_numeric(frame["best_ask"], errors="coerce")
    valid = bid.gt(0) & ask.gt(0) & bid.le(ask)
    return float(valid.mean())


def _parseable_depth_rate(frame: pd.DataFrame | None) -> float:
    if frame is None or frame.empty:
        return 0.0

    def valid(value: Any) -> bool:
        try:
            payload = value if isinstance(value, Mapping) else json.loads(value)
        except Exception:
            return False
        if not isinstance(payload, Mapping):
            return False
        depth = payload.get("depth", payload)
        if not isinstance(depth, Mapping):
            return False
        buy = depth.get("buy")
        sell = depth.get("sell")
        return bool(isinstance(buy, list) and isinstance(sell, list))

    return float(frame["depth_json"].map(valid).mean())


def _session_dates(frame: pd.DataFrame | None) -> set[str]:
    if frame is None or frame.empty or "local_ts" not in frame:
        return set()
    values = pd.to_datetime(frame["local_ts"], errors="coerce")
    return set(values.dropna().dt.date.astype(str))


def audit_data_readiness(
    *,
    futures_ticks: pd.DataFrame | None,
    option_ticks: pd.DataFrame | None,
    instrument_master: pd.DataFrame | None,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    missing_futures = _missing_columns(futures_ticks, _REQUIRED_FUTURES)
    missing_options = _missing_columns(option_ticks, _REQUIRED_OPTIONS)
    missing_master = _missing_columns(instrument_master, _REQUIRED_MASTER)
    if futures_ticks is None:
        blockers.append("MISSING_FUTURES_TICK_DATASET")
    if option_ticks is None:
        blockers.append("MISSING_OPTION_TICK_DATASET")
    if instrument_master is None:
        blockers.append("MISSING_SAME_DAY_INSTRUMENT_MASTER")
    if missing_futures:
        blockers.append(
            "FUTURES_FIELDS_MISSING:" + ",".join(missing_futures)
        )
    if missing_options:
        blockers.append(
            "OPTION_FIELDS_MISSING:" + ",".join(missing_options)
        )
    if missing_master:
        blockers.append(
            "INSTRUMENT_MASTER_FIELDS_MISSING:" + ",".join(missing_master)
        )

    futures_quote_rate = 0.0
    option_quote_rate = 0.0
    futures_depth_rate = 0.0
    option_depth_rate = 0.0
    overlapping_sessions: set[str] = set()
    option_expiries = 0
    resolved_option_tokens = 0
    option_token_count = 0
    if not missing_futures and futures_ticks is not None:
        futures_quote_rate = _valid_quote_rate(futures_ticks)
        futures_depth_rate = _parseable_depth_rate(futures_ticks)
        if futures_quote_rate < 0.99:
            blockers.append("FUTURES_EXECUTABLE_QUOTE_RATE_BELOW_99_PERCENT")
        if futures_depth_rate < 0.99:
            blockers.append("FUTURES_DEPTH_PARSE_RATE_BELOW_99_PERCENT")
    if not missing_options and option_ticks is not None:
        option_quote_rate = _valid_quote_rate(option_ticks)
        option_depth_rate = _parseable_depth_rate(option_ticks)
        if option_quote_rate < 0.99:
            blockers.append("OPTION_EXECUTABLE_QUOTE_RATE_BELOW_99_PERCENT")
        if option_depth_rate < 0.99:
            blockers.append("OPTION_DEPTH_PARSE_RATE_BELOW_99_PERCENT")
    if (
        futures_ticks is not None
        and option_ticks is not None
        and not missing_futures
        and not missing_options
    ):
        overlapping_sessions = _session_dates(futures_ticks).intersection(
            _session_dates(option_ticks)
        )
        minimum_sessions = int(
            specification["required_input_contract"]["minimum_sessions"]
        )
        if len(overlapping_sessions) < minimum_sessions:
            blockers.append(
                f"INSUFFICIENT_OVERLAPPING_SESSIONS:{len(overlapping_sessions)}"
            )
    if (
        option_ticks is not None
        and instrument_master is not None
        and not missing_options
        and not missing_master
    ):
        option_tokens = set(
            pd.to_numeric(
                option_ticks["instrument_token"], errors="coerce"
            ).dropna().astype(int)
        )
        master = instrument_master.copy()
        master["instrument_token"] = pd.to_numeric(
            master["instrument_token"], errors="coerce"
        )
        master = master.dropna(subset=["instrument_token"])
        master["instrument_token"] = master["instrument_token"].astype(int)
        option_rows = master[
            master["instrument_type"].astype(str).str.upper().isin({"CE", "PE"})
        ]
        resolved = option_rows[
            option_rows["instrument_token"].isin(option_tokens)
        ]
        option_token_count = len(option_tokens)
        resolved_option_tokens = int(resolved["instrument_token"].nunique())
        option_expiries = int(
            pd.to_datetime(resolved["expiry"], errors="coerce").dropna().nunique()
        )
        if resolved_option_tokens != option_token_count:
            blockers.append("UNRESOLVED_OPTION_TOKENS")
        if option_expiries < int(
            specification["required_input_contract"][
                "minimum_expiries_per_session"
            ]
        ):
            blockers.append("INSUFFICIENT_EXPIRY_COVERAGE")
        available_types = set(
            resolved["instrument_type"].astype(str).str.upper().unique()
        )
        if not {"CE", "PE"}.issubset(available_types):
            blockers.append("BOTH_CE_AND_PE_REQUIRED")

    blockers = sorted(set(blockers))
    return {
        "ready": not blockers,
        "verdict": (
            "DATA_READY_FOR_DEVELOPMENT"
            if not blockers
            else "BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA"
        ),
        "blockers": blockers,
        "futures_rows": 0 if futures_ticks is None else int(len(futures_ticks)),
        "option_rows": 0 if option_ticks is None else int(len(option_ticks)),
        "instrument_master_rows": (
            0 if instrument_master is None else int(len(instrument_master))
        ),
        "overlapping_sessions": len(overlapping_sessions),
        "option_expiries": option_expiries,
        "option_token_count": option_token_count,
        "resolved_option_tokens": resolved_option_tokens,
        "futures_executable_quote_rate": futures_quote_rate,
        "option_executable_quote_rate": option_quote_rate,
        "futures_depth_parse_rate": futures_depth_rate,
        "option_depth_parse_rate": option_depth_rate,
        "required_inputs": {
            "futures_ticks": list(_REQUIRED_FUTURES),
            "option_ticks": list(_REQUIRED_OPTIONS),
            "instrument_master": list(_REQUIRED_MASTER),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def development_evidence_from_readiness(
    readiness: Mapping[str, Any],
    *,
    specification: Mapping[str, Any],
    frozen_spec_sha256: str,
    code_sha: str,
    input_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if readiness.get("ready") is True:
        verdict = "BLOCKED_NEED_DORL_DEVELOPMENT_SCREEN"
    else:
        verdict = "BLOCKED_NEED_OPTION_MICROSTRUCTURE_DATA"
    return {
        "schema_version": "1.0",
        "stage": "development",
        "hypothesis_id": specification["hypothesis_id"],
        "family": specification["family"],
        "frozen_spec_sha256": frozen_spec_sha256,
        "code_sha": code_sha,
        "input_hashes": dict(sorted((input_hashes or {}).items())),
        "verdict": verdict,
        "candidate_count": 0,
        "candidate_bundle_hash": None,
        "candidate": None,
        "data_readiness": dict(readiness),
        "validation_v1_consumed_loaded": False,
        "holdout_v1_locked_loaded": False,
        "fresh_confirmation_loaded": False,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "claim_boundary": "NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN",
    }


def load_table(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise RepricingLagError(f"dataset is missing: {resolved}")
    suffix = resolved.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(resolved)
    if suffix == ".csv":
        return pd.read_csv(resolved)
    if suffix == ".json":
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, Mapping):
            return pd.DataFrame([payload])
    raise RepricingLagError(f"unsupported dataset type: {resolved.suffix}")


def file_sha256(path: str | Path | None) -> str | None:
    if path is None:
        return None
    resolved = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "audit_data_readiness",
    "development_evidence_from_readiness",
    "file_sha256",
    "load_table",
]
