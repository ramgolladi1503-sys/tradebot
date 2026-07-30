from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

STAGE2 = Path("information-migration-sequence-v1-stage2")
OUT = Path("information-migration-sequence-v1-stage3")
BOOTSTRAP_SEED = 759031
BOOTSTRAP_DRAWS = 5000


def _metrics(frame: pd.DataFrame, column: str) -> dict:
    data = frame[["session", column]].dropna().copy()
    values = data[column].astype(float)
    wins = values[values > 0]
    losses = values[values <= 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_win = float(wins.mean()) if len(wins) else float("nan")
    avg_loss = float(-losses.mean()) if len(losses) else float("nan")
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

    low, high = values.quantile([0.05, 0.95])
    winsorized = values.clip(lower=low, upper=high)
    session_means = data.groupby("session")[column].mean()

    positive = values[values > 0].sort_values(ascending=False)
    positive_total = float(positive.sum())
    top5_share = float(positive.head(5).sum() / positive_total) if positive_total > 0 else float("nan")

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sessions = session_means.index.to_numpy()
    boot = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    for i in range(BOOTSTRAP_DRAWS):
        sampled = rng.choice(sessions, size=len(sessions), replace=True)
        boot[i] = float(session_means.loc[sampled].mean())

    return {
        "trades": int(len(values)),
        "sessions": int(session_means.size),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "win_rate": float((values > 0).mean()),
        "average_win": avg_win,
        "average_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "winsorized_5_95_mean": float(winsorized.mean()),
        "positive_session_rate": float((session_means > 0).mean()),
        "session_mean_median": float(session_means.median()),
        "top5_positive_contribution_share": top5_share,
        "bootstrap_session_mean_p10": float(np.quantile(boot, 0.10)),
        "bootstrap_session_mean_p50": float(np.quantile(boot, 0.50)),
        "bootstrap_session_mean_p90": float(np.quantile(boot, 0.90)),
    }


def main() -> None:
    stage2_report_path = STAGE2 / "stage2_report.json"
    trades_path = STAGE2 / "attached_option_trades.parquet"
    if not stage2_report_path.exists() or not trades_path.exists():
        raise SystemExit("Stage 2 evidence missing")

    stage2 = json.loads(stage2_report_path.read_text())
    if stage2.get("holdout_evaluated"):
        raise SystemExit("holdout contamination detected")
    horizon = stage2.get("selected_horizon_minutes")
    if horizon is None:
        raise SystemExit("no development-selected horizon")

    trades = pd.read_parquet(trades_path)
    column = f"net_return_{int(horizon)}m"
    development = _metrics(trades.loc[trades["split"].eq("development")], column)
    validation = _metrics(trades.loc[trades["split"].eq("validation")], column)

    passes = (
        development["mean"] > 0
        and development["profit_factor"] > 1.05
        and validation["mean"] > 0
        and validation["profit_factor"] > 1.05
        and validation["winsorized_5_95_mean"] > 0
        and validation["top5_positive_contribution_share"] < 0.50
        and validation["bootstrap_session_mean_p10"] > -0.005
    )
    verdict = "ASYMMETRIC_EDGE_CANDIDATE_READY_FOR_SEALED_HOLDOUT" if passes else "TAIL_DRIVEN_OR_UNSTABLE_NO_EDGE"

    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "research_only": True,
        "allowed_for_live_execution": False,
        "selected_horizon_minutes": int(horizon),
        "development_metrics": development,
        "validation_metrics": validation,
        "holdout_evaluated": False,
        "holdout_sessions_sealed": stage2["holdout_sessions_sealed"],
        "principal_verdict": verdict,
        "next_stage": "single sealed holdout evaluation with frozen rules" if passes else "reject tested information migration family",
    }
    (OUT / "stage3_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
