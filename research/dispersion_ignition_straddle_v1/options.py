from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import DataContractError, FRICTIONS, HORIZONS, normalize_timestamp


def resolve_contract_path(root: Path, relative: Any) -> Path:
    value = str(relative or "").strip()
    if not value:
        raise DataContractError("empty normalized option path")
    direct = root / value
    if direct.exists():
        return direct
    parts = Path(value).parts
    for pos in range(len(parts)):
        candidate = root.joinpath(*parts[pos:])
        if candidate.exists():
            return candidate
    matches = list(root.rglob(Path(value).name))
    if len(matches) == 1:
        return matches[0]
    raise DataContractError(f"cannot resolve option path: {value}")


class OptionPairStore:
    def __init__(self, inventory_path: Path, option_root: Path):
        inventory = pd.read_parquet(inventory_path).copy()
        required = {"expiry", "strike", "option_type", "normalized_1m_path"}
        missing = sorted(required - set(inventory.columns))
        if missing:
            raise DataContractError(f"contract inventory missing: {missing}")
        inventory["expiry"] = pd.to_datetime(inventory["expiry"], errors="coerce").dt.date
        inventory["strike"] = pd.to_numeric(inventory["strike"], errors="coerce")
        inventory["option_type"] = inventory["option_type"].astype(str).str.upper()
        inventory = inventory.dropna(subset=["expiry", "strike", "normalized_1m_path"])
        if "final_status" in inventory:
            inventory = inventory[inventory["final_status"].isin(["VALID_COMPLETE", "VALID_1M_ONLY"])]
        pairs = inventory.pivot_table(
            index=["expiry", "strike"], columns="option_type", values="normalized_1m_path", aggfunc="first"
        ).reset_index()
        if "CE" not in pairs or "PE" not in pairs:
            raise DataContractError("no same-strike CE/PE pairs")
        self.pairs = pairs.dropna(subset=["CE", "PE"]).sort_values(["expiry", "strike"])
        self.option_root = option_root
        self.cache: dict[Path, pd.DataFrame] = {}

    def _load(self, relative: str) -> pd.DataFrame:
        path = resolve_contract_path(self.option_root, relative)
        if path not in self.cache:
            frame = pd.read_parquet(path).copy()
            required = {"timestamp", "open", "high", "low", "close"}
            missing = sorted(required - set(frame.columns))
            if missing:
                raise DataContractError(f"{path} missing: {missing}")
            frame["timestamp"] = normalize_timestamp(frame["timestamp"])
            for column in ("open", "high", "low", "close", "volume", "open_interest"):
                if column not in frame:
                    frame[column] = 0.0
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
            frame = frame.sort_values("timestamp", kind="mergesort").drop_duplicates("timestamp", keep="last")
            self.cache[path] = frame.set_index("timestamp", drop=False)
        return self.cache[path]

    def select(self, session: str, signal_timestamp: pd.Timestamp, spot: float) -> dict[str, Any] | None:
        session_date = pd.Timestamp(session).date()
        eligible = self.pairs[self.pairs["expiry"] >= session_date]
        if eligible.empty:
            return None
        expiry = eligible["expiry"].min()
        eligible = eligible[eligible["expiry"] == expiry].copy()
        eligible["distance"] = (eligible["strike"] - float(spot)).abs()
        eligible = eligible[eligible["distance"] <= 100.0]
        if eligible.empty:
            return None
        row = eligible.sort_values(["distance", "strike"], kind="mergesort").iloc[0]
        ce, pe = self._load(str(row["CE"])), self._load(str(row["PE"]))
        prior = signal_timestamp - pd.Timedelta(minutes=1)
        if prior not in ce.index or prior not in pe.index:
            return None
        return {"expiry": str(expiry), "strike": float(row["strike"]), "ce": ce, "pe": pe, "prior": prior}


def stale_at_signal(frame: pd.DataFrame, timestamp: pd.Timestamp) -> bool:
    if "stale_price_flag" in frame and timestamp in frame.index:
        value = frame.loc[timestamp, "stale_price_flag"]
        if isinstance(value, pd.Series):
            value = value.iloc[-1]
        if pd.notna(value) and bool(value):
            return True
    window = frame.loc[:timestamp].tail(3)
    return bool(len(window) == 3 and window["close"].nunique() == 1 and window["volume"].fillna(0).sum() == 0)


def replay_signal(store: OptionPairStore, signal: pd.Series, delay: int = 0) -> list[dict[str, Any]]:
    pair = store.select(str(signal["session"]), signal["signal_timestamp"], float(signal["index_close"]))
    if pair is None or stale_at_signal(pair["ce"], pair["prior"]) or stale_at_signal(pair["pe"], pair["prior"]):
        return []
    ce, pe = pair["ce"], pair["pe"]
    zero_volume = bool(float(ce.loc[pair["prior"], "volume"]) <= 0 or float(pe.loc[pair["prior"], "volume"]) <= 0)
    entry_ts = signal["signal_timestamp"] + pd.Timedelta(minutes=delay)
    if entry_ts not in ce.index or entry_ts not in pe.index:
        return []
    ce_entry, pe_entry = float(ce.loc[entry_ts, "open"]), float(pe.loc[entry_ts, "open"])
    entered = ce_entry + pe_entry
    if not np.isfinite(entered) or entered <= 0:
        return []
    records = []
    for horizon in HORIZONS:
        exit_ts = entry_ts + pd.Timedelta(minutes=horizon - 1)
        if exit_ts not in ce.index or exit_ts not in pe.index:
            continue
        ce_exit, pe_exit = float(ce.loc[exit_ts, "close"]), float(pe.loc[exit_ts, "close"])
        gross = (ce_exit + pe_exit - entered) / entered
        records.append({
            "session": str(signal["session"]), "signal_timestamp": signal["signal_timestamp"],
            "entry_timestamp": entry_ts, "exit_timestamp": exit_ts, "variant": signal["variant"],
            "fold": int(signal.get("fold", -1)), "horizon": horizon, "expiry": pair["expiry"],
            "strike": pair["strike"], "index_close": float(signal["index_close"]),
            "ce_entry": ce_entry, "pe_entry": pe_entry, "ce_exit": ce_exit, "pe_exit": pe_exit,
            "entered_premium": entered, "gross_return": gross,
            "base_return": gross - FRICTIONS["base"], "stress_return": gross - FRICTIONS["stress"],
            "severe_return": gross - FRICTIONS["severe"], "prior_zero_volume": zero_volume,
            "extra_entry_delay": delay, "future_range": float(signal.get(f"future_range_{horizon}", np.nan)),
        })
    return records


def replay_frame(store: OptionPairStore, signals: pd.DataFrame, delay: int = 0) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for _, signal in signals.sort_values(["session", "signal_timestamp", "variant"]).iterrows():
        records.extend(replay_signal(store, signal, delay))
    return pd.DataFrame(records)
