from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


class ContractSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class ContractSelection:
    contract_symbol: str
    underlying: str
    option_type: str
    strike: float
    expiry: str
    catalog_time_authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_symbol": self.contract_symbol,
            "underlying": self.underlying,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiry": self.expiry,
            "catalog_time_authority": self.catalog_time_authority,
        }


def _normalise_direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BULLISH", "LONG", "UP", "BUY", "CE"}:
        return "BULLISH"
    if text in {"BEARISH", "SHORT", "DOWN", "SELL", "PE"}:
        return "BEARISH"
    if text in {"NEUTRAL", "NONE", "NO_TRADE", "FLAT", ""}:
        return "NEUTRAL"
    raise ContractSelectionError(f"invalid_direction:{text}")


def option_type_for_direction(direction: Any) -> str | None:
    normalised = _normalise_direction(direction)
    if normalised == "BULLISH":
        return "CE"
    if normalised == "BEARISH":
        return "PE"
    return None


def select_contract(
    *,
    signal: pd.Series,
    catalog: pd.DataFrame,
    timezone: str,
    require_session_catalog: bool,
) -> ContractSelection | None:
    direction = _normalise_direction(signal.get("direction"))
    option_type = option_type_for_direction(direction)
    if option_type is None:
        return None

    signal_ts = pd.Timestamp(signal["signal_ts"])
    if signal_ts.tzinfo is None:
        signal_ts = signal_ts.tz_localize(timezone)
    else:
        signal_ts = signal_ts.tz_convert(timezone)

    underlying = str(signal.get("underlying") or "").strip().upper()
    if not underlying:
        raise ContractSelectionError("missing_underlying")
    spot = pd.to_numeric(pd.Series([signal.get("underlying_price")]), errors="coerce").iloc[0]
    if pd.isna(spot) or float(spot) <= 0:
        raise ContractSelectionError("invalid_underlying_price")

    required = {"contract_symbol", "underlying", "option_type", "strike", "expiry"}
    missing = sorted(required - set(catalog.columns))
    if missing:
        raise ContractSelectionError(f"missing_catalog_columns:{','.join(missing)}")

    work = catalog.copy()
    work["underlying"] = work["underlying"].astype(str).str.strip().str.upper()
    work["option_type"] = work["option_type"].astype(str).str.strip().str.upper().replace({"CALL": "CE", "PUT": "PE"})
    work["strike"] = pd.to_numeric(work["strike"], errors="coerce")
    work["expiry"] = pd.to_datetime(work["expiry"], errors="coerce").dt.date
    work = work.loc[
        (work["underlying"] == underlying)
        & (work["option_type"] == option_type)
        & work["strike"].notna()
        & work["expiry"].notna()
        & (work["expiry"] >= signal_ts.date())
    ].copy()

    catalog_time_authority = "STATIC_CATALOG_LIMITATION"
    if "session_date" in work.columns:
        session_dates = pd.to_datetime(work["session_date"], errors="coerce").dt.date
        session_rows = work.loc[session_dates == signal_ts.date()].copy()
        if not session_rows.empty:
            work = session_rows
            catalog_time_authority = "SESSION_BOUND_CATALOG"
        elif require_session_catalog:
            raise ContractSelectionError("missing_session_catalog_rows")
    elif require_session_catalog:
        raise ContractSelectionError("missing_session_date_column")

    if work.empty:
        raise ContractSelectionError("no_eligible_contract")

    nearest_expiry = min(work["expiry"])
    work = work.loc[work["expiry"] == nearest_expiry].copy()
    work["strike_distance"] = (work["strike"] - float(spot)).abs()
    work = work.sort_values(
        ["strike_distance", "strike", "contract_symbol"],
        ascending=[True, True, True],
        kind="mergesort",
    )
    chosen = work.iloc[0]
    return ContractSelection(
        contract_symbol=str(chosen["contract_symbol"]),
        underlying=underlying,
        option_type=option_type,
        strike=float(chosen["strike"]),
        expiry=chosen["expiry"].isoformat(),
        catalog_time_authority=catalog_time_authority,
    )
