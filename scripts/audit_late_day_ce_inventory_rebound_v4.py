#!/usr/bin/env python3
"""Independent horizon/economics audit for Late-Day CE Inventory Rebound V3.

Reconstructs 5/10/15/20-minute close outcomes directly from preserved option
OHLCV. It does not import the discovery implementation. It detects the V3
contract defect: the published contract says 20 minutes, while the consumed
outcome labels and ledger economics are five-minute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

PRIOR_REL = Path(
    "research/local_evidence_consolidation_v1/worktrees/"
    "reverse-causal-option-expansion-v1/runtime_research/"
    "reverse_causal_option_expansion_v1"
)
EVENT_FILE = "event_universe_5m.parquet"
V3_REL = Path("runtime/research/late_day_ce_inventory_rebound_v3")
OUT_REL = Path("runtime/research/late_day_ce_inventory_rebound_v4_horizon_audit")
RESEARCH_REL = Path("research/late_day_ce_inventory_rebound_v4_horizon_audit")
SEED = 20260729
NORMAL_COST = 0.10
STRESS_COST = 1.00
HORIZONS = (5, 10, 15, 20)


@dataclass(frozen=True)
class Metrics:
    trades: int
    profit_factor: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    win_rate: float | None
    net_return_pct_sum: float
    remove_top_two_profit_factor: float | None
    stress_profit_factor: float | None
    bootstrap_mean_ci_low: float | None
    bootstrap_mean_ci_high: float | None
    positive_folds: int
    total_folds: int
    largest_winner_share: float | None


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def profit_factor(values: Iterable[float]) -> float | None:
    clean = np.asarray(
        [float(value) for value in values if math.isfinite(float(value))],
        dtype=float,
    )
    if not len(clean):
        return None
    gross_profit = float(clean[clean > 0].sum())
    gross_loss = float(-clean[clean < 0].sum())
    return (
        gross_profit / gross_loss
        if gross_loss > 0
        else (math.inf if gross_profit > 0 else None)
    )


def bootstrap_ci(values: np.ndarray) -> tuple[float | None, float | None]:
    if len(values) < 12:
        return None, None
    rng = np.random.default_rng(SEED)
    means = np.asarray(
        [
            rng.choice(values, size=len(values), replace=True).mean()
            for _ in range(3000)
        ],
        dtype=float,
    )
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def metrics(frame: pd.DataFrame, horizon: int) -> Metrics:
    net_column = f"net_{horizon}m_pct"
    stress_column = f"stress_{horizon}m_pct"
    net = finite(frame[net_column]).dropna().to_numpy(dtype=float)
    stress = finite(frame[stress_column]).dropna().to_numpy(dtype=float)
    if not len(net):
        return Metrics(
            0, None, None, None, None, 0.0,
            None, None, None, None, 0, 0, None,
        )
    ordered = np.sort(net)[::-1]
    trimmed = ordered[2:] if len(ordered) > 2 else np.asarray([], dtype=float)
    ci_low, ci_high = bootstrap_ci(net)
    fold_means = (
        frame.groupby("fold_id", observed=True)[net_column].mean()
        if "fold_id" in frame.columns
        else pd.Series(dtype=float)
    )
    positive_sum = float(ordered[ordered > 0].sum())
    largest_share = (
        float(max(ordered[0], 0.0) / positive_sum)
        if positive_sum > 0
        else None
    )
    return Metrics(
        trades=int(len(net)),
        profit_factor=profit_factor(net),
        mean_return_pct=float(net.mean()),
        median_return_pct=float(np.median(net)),
        win_rate=float(np.mean(net > 0)),
        net_return_pct_sum=float(net.sum()),
        remove_top_two_profit_factor=profit_factor(trimmed) if len(trimmed) else None,
        stress_profit_factor=profit_factor(stress),
        bootstrap_mean_ci_low=ci_low,
        bootstrap_mean_ci_high=ci_high,
        positive_folds=int((fold_means > 0).sum()),
        total_folds=int(len(fold_means)),
        largest_winner_share=largest_share,
    )


def two_half_positive(frame: pd.DataFrame, horizon: int) -> bool:
    if len(frame) < 10:
        return False
    ordered = frame.sort_values(["session_id", "timestamp"]).reset_index(drop=True)
    halves = [
        indexes
        for indexes in np.array_split(np.arange(len(ordered)), 2)
        if len(indexes) >= 5
    ]
    column = f"net_{horizon}m_pct"
    return len(halves) == 2 and all(
        float(ordered.iloc[indexes][column].mean()) > 0
        for indexes in halves
    )


def oof_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and (metric.profit_factor or 0) >= 1.50
        and (metric.mean_return_pct or 0) > 0
        and (metric.median_return_pct or 0) > 0
        and (metric.remove_top_two_profit_factor or 0) >= 1.25
        and (metric.stress_profit_factor or 0) >= 1.25
        and (metric.bootstrap_mean_ci_low or -math.inf) > 0
        and metric.total_folds == 4
        and metric.positive_folds == 4
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.25
        )
    )


def holdout_gate(metric: Metrics, frame: pd.DataFrame, horizon: int) -> bool:
    return bool(
        metric.trades >= 10
        and (metric.profit_factor or 0) >= 1.25
        and (metric.mean_return_pct or 0) > 0
        and (metric.median_return_pct or 0) > 0
        and (metric.remove_top_two_profit_factor or 0) >= 1.05
        and (metric.stress_profit_factor or 0) >= 1.05
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.35
        )
        and two_half_positive(frame, horizon)
    )


def control_gate(
    primary: Metrics,
    mirror: Metrics,
    delayed: Metrics,
) -> bool:
    return bool(
        mirror.trades >= max(5, int(primary.trades * 0.50))
        and (primary.profit_factor or 0) >= (mirror.profit_factor or 0) + 0.25
        and (primary.mean_return_pct or -math.inf)
        > (mirror.mean_return_pct or -math.inf)
        and delayed.trades >= max(5, int(primary.trades * 0.60))
        and (delayed.profit_factor or 0) >= 1.0
        and (delayed.mean_return_pct or -math.inf) > 0
    )


def attach_exact_future_prices(
    ledger: pd.DataFrame,
    event_path: Path,
) -> pd.DataFrame:
    """Attach t+1 open and exact t+5/10/15/20 closes to ledger rows."""
    raw = pd.read_parquet(
        event_path,
        columns=[
            "expired_instrument_key",
            "timestamp",
            "session",
            "open",
            "close",
        ],
    )
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="raise", utc=True)
    raw["session_id"] = raw["session"].astype(str)
    raw["open"] = finite(raw["open"])
    raw["close"] = finite(raw["close"])
    duplicate_count = int(
        raw.duplicated(
            ["expired_instrument_key", "session_id", "timestamp"],
            keep=False,
        ).sum()
    )
    if duplicate_count:
        raise ValueError(
            f"duplicate instrument/session/timestamp rows: {duplicate_count}"
        )

    joined = ledger.copy().reset_index(drop=True)
    joined["_audit_row_id"] = np.arange(len(joined), dtype=np.int64)
    key_columns = ["expired_instrument_key", "session_id"]

    def attach(
        offset_minutes: int,
        source_column: str,
        output_column: str,
    ) -> None:
        desired = joined[
            ["_audit_row_id", *key_columns, "timestamp"]
        ].copy()
        desired["lookup_timestamp"] = (
            desired["timestamp"] + pd.Timedelta(minutes=offset_minutes)
        )
        prices = raw[
            [*key_columns, "timestamp", source_column]
        ].rename(
            columns={
                "timestamp": "lookup_timestamp",
                source_column: output_column,
            }
        )
        resolved = desired.merge(
            prices,
            on=[*key_columns, "lookup_timestamp"],
            how="left",
            validate="many_to_one",
        ).sort_values("_audit_row_id", kind="mergesort")
        joined[output_column] = resolved[output_column].to_numpy()

    attach(1, "open", "future_open_1")
    for horizon in HORIZONS:
        attach(horizon, "close", f"future_close_{horizon}")

    return joined.drop(columns=["_audit_row_id"])


def _safe_max(series: pd.Series) -> float | None:
    clean = finite(series).dropna()
    return float(clean.max()) if not clean.empty else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    ledger_path = root / V3_REL / "trade_ledger.csv"
    contract_path = root / V3_REL / "frozen_candidate_contract.json"
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    ledger = pd.read_csv(ledger_path)
    ledger["timestamp"] = pd.to_datetime(
        ledger["timestamp"],
        errors="raise",
        utc=True,
    )
    ledger["session_id"] = ledger["session_id"].astype(str)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    joined = attach_exact_future_prices(ledger, event_path)

    entry = finite(joined["entry_price_next_open"]).replace(0, np.nan)
    for horizon in HORIZONS:
        gross = (
            finite(joined[f"future_close_{horizon}"]) - entry
        ) / entry * 100.0
        joined[f"gross_{horizon}m_pct"] = gross
        joined[f"net_{horizon}m_pct"] = gross - NORMAL_COST
        joined[f"stress_{horizon}m_pct"] = gross - STRESS_COST

    entry_error = (entry - finite(joined["future_open_1"])).abs()
    forward_error = (
        finite(joined["forward_close_change_points"])
        - (finite(joined["future_close_5"]) - entry)
    ).abs()
    published_net_error = (
        finite(joined["net_return_pct"])
        - finite(joined["net_5m_pct"])
    ).abs()
    horizons_seen = sorted(
        int(value)
        for value in finite(
            joined["label_horizon_minutes"]
        ).dropna().unique()
    )
    contract_exit = str(contract.get("exit"))
    contract_mismatch = horizons_seen == [5] and "20" in contract_exit

    roles = {
        "oof": joined.loc[
            joined["ledger_role"].eq("research_oof_primary")
        ].copy(),
        "primary": joined.loc[
            joined["ledger_role"].eq("holdout_primary")
        ].copy(),
        "mirror": joined.loc[
            joined["ledger_role"].eq("holdout_mirror_control")
        ].copy(),
        "delayed": joined.loc[
            joined["ledger_role"].eq("holdout_delayed_control")
        ].copy(),
    }
    results: dict[str, Any] = {}
    for horizon in HORIZONS:
        oof_metric = metrics(roles["oof"], horizon)
        primary_metric = metrics(roles["primary"], horizon)
        mirror_metric = metrics(roles["mirror"], horizon)
        delayed_metric = metrics(roles["delayed"], horizon)
        results[str(horizon)] = {
            "oof": asdict(oof_metric),
            "holdout_primary": asdict(primary_metric),
            "holdout_mirror": asdict(mirror_metric),
            "holdout_delayed": asdict(delayed_metric),
            "oof_gate": oof_gate(oof_metric),
            "holdout_gate": holdout_gate(
                primary_metric,
                roles["primary"],
                horizon,
            ),
            "control_gate": control_gate(
                primary_metric,
                mirror_metric,
                delayed_metric,
            ),
            "oof_complete": int(
                finite(
                    roles["oof"][f"net_{horizon}m_pct"]
                ).notna().sum()
            ),
            "holdout_complete": int(
                finite(
                    roles["primary"][f"net_{horizon}m_pct"]
                ).notna().sum()
            ),
        }

    entry_max_error = _safe_max(entry_error)
    forward_max_error = _safe_max(forward_error)
    published_max_error = _safe_max(published_net_error)
    exact = bool(
        entry_max_error is not None
        and forward_max_error is not None
        and published_max_error is not None
        and entry_max_error <= 1e-9
        and forward_max_error <= 1e-9
        and published_max_error <= 1e-9
    )
    five = results["5"]
    edge_5m = bool(
        exact
        and horizons_seen == [5]
        and five["oof_gate"]
        and five["holdout_gate"]
        and five["control_gate"]
    )
    verdict = (
        "STRUCTURAL_EDGE_FOUND_LATE_DAY_CE_INVENTORY_REBOUND_"
        "5M_CANDLE_PROXY_ECONOMICS_RECONSTRUCTED"
        if edge_5m
        else "LATE_DAY_CE_INVENTORY_REBOUND_FAILED_INDEPENDENT_HORIZON_AUDIT"
    )
    payload = {
        "principal_verdict": verdict,
        "structural_edge_found_5m_candle_proxy": edge_5m,
        "v3_publication_status": (
            "INVALID_EXIT_HORIZON_CONTRACT_MISMATCH"
            if contract_mismatch
            else "NO_HORIZON_MISMATCH"
        ),
        "v3_contract_exit": contract_exit,
        "observed_label_horizons_minutes": horizons_seen,
        "entry_next_open_max_abs_error": entry_max_error,
        "five_minute_forward_close_max_abs_error": forward_max_error,
        "published_net_return_max_abs_error": published_max_error,
        "horizons": results,
        "holdout_status_for_new_horizons": (
            "ALREADY_OPENED_BY_V3_NOT_UNTOUCHED"
        ),
        "signal_membership_oracle": "NOT_PERFORMED_THIS_STAGE",
        "event_source_sha256": file_sha256(event_path),
        "v3_ledger_sha256": file_sha256(ledger_path),
        "v3_contract_sha256": file_sha256(contract_path),
        "execution_certification": (
            "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING"
        ),
        "paper_or_live_authorized": False,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    payload["semantic_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    stable_json(out / "independent_horizon_audit.json", payload)

    keep = [
        "ledger_role",
        "fold_id",
        "session_id",
        "timestamp",
        "expired_instrument_key",
        "option_type",
        "strike",
        "entry_price_next_open",
    ]
    for horizon in HORIZONS:
        keep.extend(
            [
                f"gross_{horizon}m_pct",
                f"net_{horizon}m_pct",
                f"stress_{horizon}m_pct",
            ]
        )
    joined[
        [column for column in keep if column in joined.columns]
    ].to_csv(out / "horizon_trade_ledger.csv", index=False)

    (research / "RESULT.md").write_text(
        "# Late-Day CE Inventory Rebound V4 Horizon Audit\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"V3 publication status: `{payload['v3_publication_status']}`\n\n"
        f"Observed V3 horizon: `{horizons_seen}` minutes.\n\n"
        f"Five-minute OOF metrics: "
        f"`{json.dumps(five['oof'], sort_keys=True)}`\n\n"
        f"Five-minute holdout metrics: "
        f"`{json.dumps(five['holdout_primary'], sort_keys=True)}`\n\n"
        "The V3 holdout was already opened. Results at 10/15/20 minutes are "
        "descriptive, not untouched evidence. Candle-proxy survival does not "
        "certify bid/ask execution or authorize paper/live trading.\n",
        encoding="utf-8",
    )
    return 0 if edge_5m else 4


if __name__ == "__main__":
    raise SystemExit(main())
