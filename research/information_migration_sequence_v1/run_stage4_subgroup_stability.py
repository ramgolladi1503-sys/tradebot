from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

STAGE2 = Path("information-migration-sequence-v1-stage2")
OUT = Path("information-migration-sequence-v1-stage4")
SEED = 759041
DRAWS = 3000
MIN_DEV_TRADES = 50
MIN_DEV_SESSIONS = 30
MIN_VAL_TRADES = 20


def metrics(frame: pd.DataFrame, column: str) -> dict:
    data = frame[["session", column]].dropna().copy()
    values = data[column].astype(float)
    if values.empty:
        return {"trades": 0, "sessions": 0}
    wins = values[values > 0]
    losses = values[values <= 0]
    pf = float(wins.sum() / -losses.sum()) if float(-losses.sum()) > 0 else float("inf")
    q05, q95 = values.quantile([0.05, 0.95])
    session_means = data.groupby("session")[column].mean()
    rng = np.random.default_rng(SEED)
    sessions = session_means.index.to_numpy()
    boot = np.empty(DRAWS)
    for i in range(DRAWS):
        sample = rng.choice(sessions, size=len(sessions), replace=True)
        boot[i] = float(session_means.loc[sample].mean())
    return {
        "trades": int(len(values)),
        "sessions": int(len(session_means)),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "profit_factor": pf,
        "win_rate": float((values > 0).mean()),
        "positive_session_rate": float((session_means > 0).mean()),
        "winsorized_5_95_mean": float(values.clip(q05, q95).mean()),
        "bootstrap_p10": float(np.quantile(boot, 0.10)),
        "bootstrap_p50": float(np.quantile(boot, 0.50)),
        "bootstrap_p90": float(np.quantile(boot, 0.90)),
    }


def main() -> None:
    report = json.loads((STAGE2 / "stage2_report.json").read_text())
    if report.get("holdout_evaluated"):
        raise SystemExit("holdout contamination detected")
    horizon = int(report["selected_horizon_minutes"])
    column = f"net_return_{horizon}m"
    trades = pd.read_parquet(STAGE2 / "attached_option_trades.parquet")

    subgroup_reports = {}
    eligible = []
    dev = trades.loc[trades["split"].eq("development")]
    for (group, direction), frame in dev.groupby(["group", "direction"], sort=True):
        key = f"group={int(group)}:direction={int(direction)}"
        m = metrics(frame, column)
        subgroup_reports[key] = m
        if (
            m["trades"] >= MIN_DEV_TRADES
            and m["sessions"] >= MIN_DEV_SESSIONS
            and m["mean"] > 0
            and m["profit_factor"] > 1.10
            and m["winsorized_5_95_mean"] > 0
            and m["positive_session_rate"] >= 0.45
        ):
            eligible.append({"group": int(group), "direction": int(direction), "development_metrics": m})

    selected_pairs = {(item["group"], item["direction"]) for item in eligible}
    validation = trades.loc[
        trades["split"].eq("validation")
        & trades.apply(lambda row: (int(row["group"]), int(row["direction"])) in selected_pairs, axis=1)
    ]
    validation_metrics = metrics(validation, column)
    passes = (
        bool(eligible)
        and validation_metrics.get("trades", 0) >= MIN_VAL_TRADES
        and validation_metrics.get("mean", -1) > 0
        and validation_metrics.get("profit_factor", 0) > 1.10
        and validation_metrics.get("winsorized_5_95_mean", -1) > 0
        and validation_metrics.get("bootstrap_p10", -1) > -0.01
    )
    verdict = "FROZEN_SUBGROUP_CANDIDATE_READY_FOR_SEALED_HOLDOUT" if passes else "NO_STABLE_SUBGROUP_EDGE"

    OUT.mkdir(parents=True, exist_ok=True)
    output = {
        "schema_version": 1,
        "research_only": True,
        "allowed_for_live_execution": False,
        "selected_horizon_minutes": horizon,
        "selection_source": "development only",
        "development_subgroup_metrics": subgroup_reports,
        "eligible_frozen_subgroups": eligible,
        "validation_metrics_for_frozen_subgroups": validation_metrics,
        "holdout_evaluated": False,
        "principal_verdict": verdict,
        "next_stage": "single sealed holdout evaluation" if passes else "reject tested information migration family",
    }
    (OUT / "stage4_report.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
