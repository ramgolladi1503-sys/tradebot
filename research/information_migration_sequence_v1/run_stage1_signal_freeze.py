from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

ROOT = Path("research/local_evidence_consolidation_v1")
OUT = Path("information-migration-sequence-v1-stage1")
N_GROUPS = 4
MIN_GROUP_SIZE = 4
LEADERS_PER_GROUP = 2
COOLDOWN_BARS = 3


def _first_path(name: str, preferred: str | None = None) -> Path:
    paths = sorted(ROOT.rglob(name))
    if not paths:
        raise SystemExit(f"missing {name}")
    if preferred:
        for path in paths:
            if preferred in str(path):
                return path
    return paths[0]


def _session_returns(frame: pd.DataFrame) -> pd.DataFrame:
    wide = frame.pivot_table(index=["session", "timestamp"], columns="symbol", values="close", aggfunc="last").sort_index()
    returns = wide.groupby(level=0, sort=False).pct_change(fill_method=None)
    return returns.replace([np.inf, -np.inf], np.nan)


def _jsonable(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main() -> None:
    constituent_path = _first_path("constituent_index_5m.parquet", "proxy_campaign_2024_2025_v2")
    joint_path = _first_path("repaired_joint_underlying_option_warehouse.parquet")

    c = pd.read_parquet(
        constituent_path,
        columns=["timestamp", "session", "symbol", "close", "synthetic", "mock", "fallback"],
    )
    c["timestamp"] = pd.to_datetime(c["timestamp"], utc=True, errors="coerce")
    c["session"] = pd.to_datetime(c["session"], errors="coerce").dt.date.astype(str)
    c["symbol"] = c["symbol"].astype(str)
    c["close"] = pd.to_numeric(c["close"], errors="coerce")
    c = c.loc[
        c["timestamp"].notna()
        & c["close"].gt(0)
        & ~c["synthetic"].fillna(False)
        & ~c["mock"].fillna(False)
        & ~c["fallback"].fillna(False)
    ].copy()

    jdates = pd.read_parquet(joint_path, columns=["session_date", "certified_for_replay"])
    jdates = jdates.loc[jdates["certified_for_replay"].fillna(False), "session_date"]
    certified_sessions = set(pd.to_datetime(jdates, errors="coerce").dt.date.dropna().astype(str))
    c = c.loc[c["session"].isin(certified_sessions)].copy()

    sessions = sorted(c["session"].unique().tolist())
    if len(sessions) < 120:
        raise SystemExit(f"insufficient overlapping sessions: {len(sessions)}")
    dev_end = int(len(sessions) * 0.60)
    val_end = int(len(sessions) * 0.80)
    development_sessions = sessions[:dev_end]
    validation_sessions = sessions[dev_end:val_end]
    holdout_sessions = sessions[val_end:]

    returns = _session_returns(c)
    development = returns.loc[returns.index.get_level_values("session").isin(development_sessions)]
    symbols = [symbol for symbol in development.columns if symbol != "NIFTY"]
    if "NIFTY" not in development.columns or len(symbols) < N_GROUPS * MIN_GROUP_SIZE:
        raise SystemExit("insufficient symbols or missing NIFTY")

    correlation = development[symbols].corr(min_periods=500).fillna(0.0).clip(-1.0, 1.0)
    distance_array = np.array((1.0 - correlation).clip(0.0, 2.0), dtype=float, copy=True)
    np.fill_diagonal(distance_array, 0.0)
    model = AgglomerativeClustering(n_clusters=N_GROUPS, metric="precomputed", linkage="average")
    labels = model.fit_predict(distance_array)
    groups = {int(group): sorted(correlation.columns[labels == group].tolist()) for group in sorted(set(labels))}
    undersized = {group: members for group, members in groups.items() if len(members) < MIN_GROUP_SIZE}
    if undersized:
        raise SystemExit(f"degenerate communities below minimum size {MIN_GROUP_SIZE}: {undersized}")

    leader_rows: list[dict] = []
    leaders: dict[int, list[str]] = {}
    for group, members in groups.items():
        group_returns = development[members]
        scores: list[tuple[str, float]] = []
        for symbol in members:
            peers = [member for member in members if member != symbol]
            future_peer_mean = group_returns[peers].mean(axis=1).groupby(level=0, sort=False).shift(-1)
            score = group_returns[symbol].corr(future_peer_mean)
            scores.append((symbol, float(score) if pd.notna(score) else -1.0))
        scores.sort(key=lambda item: (-item[1], item[0]))
        leaders[group] = [symbol for symbol, _ in scores[:LEADERS_PER_GROUP]]
        leader_rows.extend({"group": group, "symbol": symbol, "lead_score": score} for symbol, score in scores)

    def feature_frame(source: pd.DataFrame, group: int) -> pd.DataFrame:
        members = groups[group]
        leader_symbols = leaders[group]
        member_returns = source[members]
        leader_return = member_returns[leader_symbols].mean(axis=1)
        community_return = member_returns.mean(axis=1)
        direction = np.sign(leader_return)
        breadth = member_returns.mul(direction, axis=0).gt(0).mean(axis=1)
        nifty_return = source["NIFTY"]
        underresponse_ratio = nifty_return.abs().div(community_return.abs().replace(0.0, np.nan))
        return pd.DataFrame(
            {
                "leader_return": leader_return,
                "community_return": community_return,
                "breadth": breadth,
                "nifty_return": nifty_return,
                "underresponse_ratio": underresponse_ratio,
            }
        )

    thresholds: dict[int, dict[str, float]] = {}
    for group in groups:
        features = feature_frame(development, group).replace([np.inf, -np.inf], np.nan).dropna()
        active = features.loc[features["leader_return"].abs() > 0]
        thresholds[group] = {
            "leader_abs_q90": float(active["leader_return"].abs().quantile(0.90)),
            "breadth_q65": float(active["breadth"].quantile(0.65)),
            "underresponse_ratio_q25": float(active["underresponse_ratio"].quantile(0.25)),
        }

    evaluation_sessions = development_sessions + validation_sessions
    evaluation = returns.loc[returns.index.get_level_values("session").isin(evaluation_sessions)]
    signal_parts: list[pd.DataFrame] = []
    for group in groups:
        features = feature_frame(evaluation, group).replace([np.inf, -np.inf], np.nan).dropna()
        threshold = thresholds[group]
        selected = features.loc[
            features["leader_return"].abs().ge(threshold["leader_abs_q90"])
            & features["breadth"].ge(threshold["breadth_q65"])
            & features["underresponse_ratio"].le(threshold["underresponse_ratio_q25"])
            & features["community_return"].mul(features["leader_return"]).gt(0)
        ].copy()
        selected["group"] = group
        selected["direction"] = np.sign(selected["leader_return"]).astype(int)
        selected = selected.reset_index().sort_values(["session", "timestamp"])
        selected["bar_number"] = selected.groupby("session").cumcount()
        selected = selected.loc[selected["bar_number"].mod(COOLDOWN_BARS).eq(0)].drop(columns="bar_number")
        signal_parts.append(selected)

    signals = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()
    if not signals.empty:
        signals["split"] = np.where(signals["session"].isin(development_sessions), "development", "validation")
        signals = signals.sort_values(["timestamp", "group"]).reset_index(drop=True)

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(leader_rows).to_csv(OUT / "leader_scores.csv", index=False)
    signals.to_parquet(OUT / "frozen_signals.parquet", index=False)

    split_counts = signals["split"].value_counts().to_dict() if not signals.empty else {}
    direction_counts = signals.groupby(["split", "direction"]).size().to_dict() if not signals.empty else {}
    report = {
        "schema_version": 2,
        "research_only": True,
        "allowed_for_live_execution": False,
        "constituent_path": str(constituent_path),
        "joint_path": str(joint_path),
        "overlap_sessions": len(sessions),
        "development_sessions": len(development_sessions),
        "validation_sessions": len(validation_sessions),
        "holdout_sessions_sealed": len(holdout_sessions),
        "holdout_first_session": holdout_sessions[0],
        "holdout_last_session": holdout_sessions[-1],
        "community_count": N_GROUPS,
        "minimum_community_size": MIN_GROUP_SIZE,
        "communities": groups,
        "leaders": leaders,
        "thresholds_frozen_from_development_only": thresholds,
        "signal_count_by_split": split_counts,
        "signal_count_by_split_and_direction": {f"{k[0]}:{k[1]}": int(v) for k, v in direction_counts.items()},
        "option_outcomes_attached": False,
        "holdout_evaluated": False,
        "next_stage": "attach certified option outcomes to frozen development and validation signals only",
        "principal_verdict": "STAGE1_SIGNAL_DEFINITION_FROZEN_OUTCOME_BLIND",
    }
    (OUT / "stage1_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=_jsonable) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True, default=_jsonable))


if __name__ == "__main__":
    main()
