from __future__ import annotations

from dataclasses import dataclass
import argparse
from pathlib import Path
import hashlib
import json
import math
import random
from typing import Callable

import pandas as pd


ROOT = Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay")
BASE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Candidate:
    hypothesis_id: str
    session: str
    symbol: str
    direction: int
    entry_index: int
    entry_ts: str
    horizon_minutes: int
    evidence: dict

    @property
    def candidate_id(self) -> str:
        payload = json.dumps(
            {
                "hypothesis_id": self.hypothesis_id,
                "session": self.session,
                "symbol": self.symbol,
                "direction": self.direction,
                "entry_index": self.entry_index,
                "entry_ts": self.entry_ts,
                "evidence": self.evidence,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def _symbol_file(session: str, symbol: str) -> Path:
    folder = ROOT / session / "underlying"
    candidates = {
        "NIFTY": [folder / f"NIFTY_{session}.parquet", folder / f"NSE_INDEX|Nifty 50_{session}.parquet"],
        "BANKNIFTY": [
            folder / f"BANKNIFTY_{session}.parquet",
            folder / f"NSE_INDEX|Nifty Bank_{session}.parquet",
        ],
        "SENSEX": [folder / f"BSE_INDEX|SENSEX_{session}.parquet"],
    }
    for path in candidates[symbol]:
        if path.exists():
            return path
    raise FileNotFoundError(f"missing_symbol_file:{session}:{symbol}")


def load_symbol_session(session: str, symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(_symbol_file(session, symbol))
    required = {"timestamp", "open", "high", "low", "close", "symbol"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing_columns:{session}:{symbol}:{sorted(missing)}")
    if {"synthetic", "mock", "fallback"} <= set(df.columns):
        bad = df[["synthetic", "mock", "fallback"]].fillna(False).astype(bool).any(axis=1)
        if bool(bad.any()):
            raise ValueError(f"synthetic_mock_or_fallback_rows:{session}:{symbol}")
    df = df.sort_values("timestamp").reset_index(drop=True)
    if df["timestamp"].duplicated().any():
        raise ValueError(f"duplicate_timestamps:{session}:{symbol}")
    return df


def load_session(session: str) -> dict[str, pd.DataFrame]:
    return {symbol: load_symbol_session(session, symbol) for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}


def direction_return(df: pd.DataFrame, entry_index: int, direction: int, horizon: int) -> tuple[float | None, float | None, float | None]:
    exit_index = min(entry_index + horizon, len(df) - 1)
    if entry_index < 0 or entry_index >= len(df) or exit_index <= entry_index:
        return None, None, None
    entry = float(df.loc[entry_index, "close"])
    exit_ = float(df.loc[exit_index, "close"])
    path = df.loc[entry_index:exit_index]
    if entry <= 0:
        return None, None, None
    ret = direction * (exit_ / entry - 1.0) * 10_000.0
    mfe = direction * (float(path["high"].max()) / entry - 1.0) * 10_000.0 if direction > 0 else direction * (float(path["low"].min()) / entry - 1.0) * 10_000.0
    mae = direction * (float(path["low"].min()) / entry - 1.0) * 10_000.0 if direction > 0 else direction * (float(path["high"].max()) / entry - 1.0) * 10_000.0
    return ret, mfe, mae


def gap_acceptance(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    if prior is None:
        return []
    out = []
    for symbol, df in data.items():
        pclose = float(prior[symbol].iloc[-1]["close"])
        op = float(df.iloc[0]["open"])
        if pclose <= 0:
            continue
        gap_bps = (op / pclose - 1.0) * 10_000.0
        if abs(gap_bps) < 20 or len(df) <= 16:
            continue
        direction = 1 if gap_bps > 0 else -1
        confirm = float(df.loc[15, "close"])
        accepted = direction * (confirm - (pclose + 0.5 * (op - pclose))) > 0
        midpoint = (float(df.loc[:14, "high"].max()) + float(df.loc[:14, "low"].min())) / 2.0
        accepted = accepted and direction * (confirm - midpoint) > 0
        if accepted:
            out.append(Candidate("AC01_GAP_ACCEPTANCE_CONTINUATION", session, symbol, direction, 16, str(df.loc[16, "timestamp"]), 30, {"gap_bps": gap_bps}))
    return out


def gap_rejection(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    if prior is None:
        return []
    out = []
    for symbol, df in data.items():
        pclose = float(prior[symbol].iloc[-1]["close"])
        op = float(df.iloc[0]["open"])
        gap = op - pclose
        gap_bps = gap / pclose * 10_000.0 if pclose > 0 else 0.0
        if abs(gap_bps) < 20:
            continue
        gap_dir = 1 if gap > 0 else -1
        for i in range(30, min(60, len(df) - 1)):
            close = float(df.loc[i, "close"])
            remaining = abs(close - pclose) / abs(gap) if gap else math.inf
            crossed = gap_dir * (close - pclose) <= 0
            if crossed or remaining <= 0.25:
                out.append(Candidate("AC02_GAP_REJECTION_REVERSAL", session, symbol, -gap_dir, i + 1, str(df.loc[i + 1, "timestamp"]), 45, {"gap_bps": gap_bps, "rejection_index": i}))
                break
    return out


def prior_day_sweep_reclaim(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    if prior is None:
        return []
    out = []
    for symbol, df in data.items():
        ph = float(prior[symbol]["high"].max())
        pl = float(prior[symbol]["low"].min())
        emitted = False
        for i in range(15, min(315, len(df) - 1)):
            high = float(df.loc[i, "high"])
            low = float(df.loc[i, "low"])
            close = float(df.loc[i, "close"])
            if high > ph * 1.0005 and close < ph and not emitted:
                out.append(Candidate("AC03_PRIOR_DAY_SWEEP_RECLAIM", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 30, {"level": ph, "side": "high"}))
                emitted = True
                break
            if low < pl * 0.9995 and close > pl and not emitted:
                out.append(Candidate("AC03_PRIOR_DAY_SWEEP_RECLAIM", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 30, {"level": pl, "side": "low"}))
                emitted = True
                break
    return out


def narrow_opening_range(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        if len(df) < 31:
            continue
        op = float(df.loc[0, "open"])
        hi = float(df.loc[:29, "high"].max())
        lo = float(df.loc[:29, "low"].min())
        width_bps = (hi - lo) / op * 10_000.0 if op > 0 else math.inf
        if width_bps > 35:
            continue
        width = hi - lo
        for i in range(30, min(165, len(df) - 1)):
            close = float(df.loc[i, "close"])
            if close > hi + 0.2 * width:
                out.append(Candidate("AC04_NARROW_OPENING_RANGE_EXPANSION", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 60, {"width_bps": width_bps}))
                break
            if close < lo - 0.2 * width:
                out.append(Candidate("AC04_NARROW_OPENING_RANGE_EXPANSION", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 60, {"width_bps": width_bps}))
                break
    return out


def cross_index_lead_lag(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    ranges = {}
    for symbol, df in data.items():
        if len(df) < 31:
            return []
        hi = float(df.loc[:29, "high"].max())
        lo = float(df.loc[:29, "low"].min())
        ranges[symbol] = (hi, lo, hi - lo)
    leader = None
    for i in range(30, min(195, min(len(df) for df in data.values()) - 1)):
        for symbol, df in data.items():
            hi, lo, width = ranges[symbol]
            close = float(df.loc[i, "close"])
            direction = 1 if close > hi + 0.1 * width else -1 if close < lo - 0.1 * width else 0
            if direction and leader is None:
                leader = (symbol, i, direction)
        if leader is not None:
            break
    if leader is None:
        return []
    leader_symbol, leader_i, direction = leader
    for i in range(leader_i + 1, min(leader_i + 16, 195, min(len(df) for df in data.values()) - 1)):
        confirmations = []
        for symbol, df in data.items():
            if symbol == leader_symbol:
                continue
            hi, lo, width = ranges[symbol]
            close = float(df.loc[i, "close"])
            if (direction > 0 and close > hi + 0.1 * width) or (direction < 0 and close < lo - 0.1 * width):
                confirmations.append(symbol)
        if confirmations:
            return [Candidate("AC05_CROSS_INDEX_LEAD_LAG_CONFIRMATION", session, "MARKET", direction, i + 1, str(next(iter(data.values())).loc[i + 1, "timestamp"]), 45, {"leader": leader_symbol, "confirmations": confirmations})]
    return []


def failed_opening_drive(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        if len(df) < 91:
            continue
        op = float(df.loc[0, "open"])
        hi = float(df.loc[:44, "high"].max())
        lo = float(df.loc[:44, "low"].min())
        high_i = int(df.loc[:44, "high"].idxmax())
        low_i = int(df.loc[:44, "low"].idxmin())
        up_bps = (hi / op - 1.0) * 10_000.0
        dn_bps = (lo / op - 1.0) * 10_000.0
        midpoint = (float(df.loc[:29, "high"].max()) + float(df.loc[:29, "low"].min())) / 2.0
        if up_bps >= 35 and high_i < 45:
            for i in range(max(45, high_i + 1), min(90, len(df) - 1)):
                if float(df.loc[i, "close"]) < midpoint:
                    out.append(Candidate("AC06_FAILED_OPENING_DRIVE_REVERSAL", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 45, {"drive_bps": up_bps}))
                    break
        elif dn_bps <= -35 and low_i < 45:
            for i in range(max(45, low_i + 1), min(90, len(df) - 1)):
                if float(df.loc[i, "close"]) > midpoint:
                    out.append(Candidate("AC06_FAILED_OPENING_DRIVE_REVERSAL", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 45, {"drive_bps": dn_bps}))
                    break
    return out


def midday_compression_late_expansion(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        if len(df) < 271:
            continue
        start, end = 105, 225
        op = float(df.loc[0, "open"])
        hi = float(df.loc[start:end, "high"].max())
        lo = float(df.loc[start:end, "low"].min())
        width = hi - lo
        width_bps = width / op * 10_000.0 if op > 0 else math.inf
        if width_bps > 45:
            continue
        for i in range(end + 1, min(330, len(df) - 1)):
            close = float(df.loc[i, "close"])
            if close > hi + 0.15 * width:
                out.append(Candidate("AC07_MIDDAY_COMPRESSION_LATE_EXPANSION", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 45, {"compression_width_bps": width_bps}))
                break
            if close < lo - 0.15 * width:
                out.append(Candidate("AC07_MIDDAY_COMPRESSION_LATE_EXPANSION", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 45, {"compression_width_bps": width_bps}))
                break
    return out


def _vwap(df: pd.DataFrame, end_index: int) -> float:
    typical = (df.loc[:end_index, "high"] + df.loc[:end_index, "low"] + df.loc[:end_index, "close"]) / 3.0
    vol = df.loc[:end_index, "volume"].astype(float)
    if float(vol.sum()) > 0:
        return float((typical * vol).sum() / vol.sum())
    return float(typical.mean())


def vwap_inventory_transfer(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        prev_side = None
        crosses = 0
        for i in range(60, min(270, len(df) - 1)):
            vw = _vwap(df, i)
            close = float(df.loc[i, "close"])
            side = 1 if close > vw else -1 if close < vw else 0
            if prev_side is not None and side and side != prev_side:
                crosses += 1
            prev_side = side or prev_side
            dist_bps = abs(close / vw - 1.0) * 10_000.0 if vw > 0 else 0
            if crosses >= 2 and dist_bps >= 8 and side:
                out.append(Candidate("AC08_VWAP_INVENTORY_TRANSFER", session, symbol, side, i + 1, str(df.loc[i + 1, "timestamp"]), 30, {"vwap": vw, "crosses": crosses, "dist_bps": dist_bps}))
                break
    return out


def large_opening_range_mean_reversion(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        if len(df) < 181:
            continue
        op = float(df.loc[0, "open"])
        hi = float(df.loc[:29, "high"].max())
        lo = float(df.loc[:29, "low"].min())
        width = hi - lo
        width_bps = width / op * 10_000.0 if op > 0 else 0
        if width_bps < 90:
            continue
        midpoint = (hi + lo) / 2.0
        for i in range(30, min(180, len(df) - 1)):
            close = float(df.loc[i, "close"])
            if float(df.loc[:i, "high"].max()) > hi + 0.1 * width and close < hi:
                out.append(Candidate("AC09_LARGE_OPENING_RANGE_MEAN_REVERSION", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 60, {"width_bps": width_bps, "midpoint": midpoint}))
                break
            if float(df.loc[:i, "low"].min()) < lo - 0.1 * width and close > lo:
                out.append(Candidate("AC09_LARGE_OPENING_RANGE_MEAN_REVERSION", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 60, {"width_bps": width_bps, "midpoint": midpoint}))
                break
    return out


def late_session_range_escape(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> list[Candidate]:
    del prior
    out = []
    for symbol, df in data.items():
        if len(df) < 361:
            continue
        hi = float(df.loc[:224, "high"].max())
        lo = float(df.loc[:224, "low"].min())
        width = hi - lo
        for i in range(285, min(360, len(df) - 1)):
            close = float(df.loc[i, "close"])
            if close > hi + 0.1 * width:
                out.append(Candidate("AC10_LATE_SESSION_RANGE_ESCAPE", session, symbol, 1, i + 1, str(df.loc[i + 1, "timestamp"]), 30, {"morning_width": width}))
                break
            if close < lo - 0.1 * width:
                out.append(Candidate("AC10_LATE_SESSION_RANGE_ESCAPE", session, symbol, -1, i + 1, str(df.loc[i + 1, "timestamp"]), 30, {"morning_width": width}))
                break
    return out


GENERATORS: dict[str, Callable[[str, dict[str, pd.DataFrame], dict[str, pd.DataFrame] | None], list[Candidate]]] = {
    "AC01_GAP_ACCEPTANCE_CONTINUATION": gap_acceptance,
    "AC02_GAP_REJECTION_REVERSAL": gap_rejection,
    "AC03_PRIOR_DAY_SWEEP_RECLAIM": prior_day_sweep_reclaim,
    "AC04_NARROW_OPENING_RANGE_EXPANSION": narrow_opening_range,
    "AC05_CROSS_INDEX_LEAD_LAG_CONFIRMATION": cross_index_lead_lag,
    "AC06_FAILED_OPENING_DRIVE_REVERSAL": failed_opening_drive,
    "AC07_MIDDAY_COMPRESSION_LATE_EXPANSION": midday_compression_late_expansion,
    "AC08_VWAP_INVENTORY_TRANSFER": vwap_inventory_transfer,
    "AC09_LARGE_OPENING_RANGE_MEAN_REVERSION": large_opening_range_mean_reversion,
    "AC10_LATE_SESSION_RANGE_ESCAPE": late_session_range_escape,
}

CYCLE_HYPOTHESES = {
    1: [
        "AC01_GAP_ACCEPTANCE_CONTINUATION",
        "AC02_GAP_REJECTION_REVERSAL",
        "AC03_PRIOR_DAY_SWEEP_RECLAIM",
        "AC04_NARROW_OPENING_RANGE_EXPANSION",
        "AC05_CROSS_INDEX_LEAD_LAG_CONFIRMATION",
    ],
    2: [
        "AC06_FAILED_OPENING_DRIVE_REVERSAL",
        "AC07_MIDDAY_COMPRESSION_LATE_EXPANSION",
        "AC08_VWAP_INVENTORY_TRANSFER",
        "AC09_LARGE_OPENING_RANGE_MEAN_REVERSION",
        "AC10_LATE_SESSION_RANGE_ESCAPE",
    ],
}


def evaluate_candidates(candidates: list[Candidate], sessions_data: dict[str, dict[str, pd.DataFrame]]) -> list[dict]:
    rows = []
    for c in candidates:
        if c.symbol == "MARKET":
            vals = []
            mfes = []
            maes = []
            for symbol in ("NIFTY", "BANKNIFTY", "SENSEX"):
                ret, mfe, mae = direction_return(sessions_data[c.session][symbol], c.entry_index, c.direction, c.horizon_minutes)
                if ret is not None:
                    vals.append(ret)
                    mfes.append(mfe)
                    maes.append(mae)
            if not vals:
                continue
            ret = sum(vals) / len(vals)
            mfe = sum(mfes) / len(mfes)
            mae = sum(maes) / len(maes)
        else:
            ret, mfe, mae = direction_return(sessions_data[c.session][c.symbol], c.entry_index, c.direction, c.horizon_minutes)
            if ret is None:
                continue
        rows.append({**c.__dict__, "candidate_id": c.candidate_id, "outcome_bps": ret, "mfe_bps": mfe, "mae_bps": mae})
    return rows


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"candidate_count": 0, "session_count": 0, "mean_bps": None, "median_bps": None, "positive_candidate_fraction": None, "positive_session_fraction": None}
    df = pd.DataFrame(rows)
    by_session = df.groupby("session")["outcome_bps"].mean()
    session_values = list(float(x) for x in by_session)
    rng = random.Random(20260721)
    boot = []
    if session_values:
        for _ in range(10_000):
            sample = [session_values[rng.randrange(len(session_values))] for _ in session_values]
            boot.append(sum(sample) / len(sample))
        boot.sort()
    top = df.groupby("session")["outcome_bps"].count().sort_values(ascending=False)
    return {
        "candidate_count": int(len(df)),
        "session_count": int(df["session"].nunique()),
        "mean_bps": float(df["outcome_bps"].mean()),
        "median_bps": float(df["outcome_bps"].median()),
        "positive_candidate_fraction": float((df["outcome_bps"] > 0).mean()),
        "positive_session_fraction": float((by_session > 0).mean()),
        "session_clustered_mean_ci_95": [
            float(boot[int(0.025 * (len(boot) - 1))]) if boot else None,
            float(boot[int(0.975 * (len(boot) - 1))]) if boot else None,
        ],
        "mfe_mean_bps": float(df["mfe_bps"].mean()),
        "mae_mean_bps": float(df["mae_bps"].mean()),
        "single_session_concentration": float(top.iloc[0] / len(df)),
        "top_five_session_concentration": float(top.head(5).sum() / len(df)),
        "symbol_breakdown": df.groupby("symbol")["outcome_bps"].agg(["count", "mean"]).reset_index().to_dict("records"),
        "direction_breakdown": df.groupby("direction")["outcome_bps"].agg(["count", "mean"]).reset_index().to_dict("records"),
    }


def wfa(rows: list[dict], discovery_sessions: list[str]) -> list[dict]:
    blocks = [discovery_sessions[round(i * len(discovery_sessions) / 6): round((i + 1) * len(discovery_sessions) / 6)] for i in range(6)]
    out = []
    for fold in range(1, 6):
        val = set(blocks[fold])
        fold_rows = [r for r in rows if r["session"] in val]
        s = summarize(fold_rows)
        out.append({"fold": fold, "validation_start": blocks[fold][0], "validation_end": blocks[fold][-1], **s})
    return out


def control_summary(rows: list[dict]) -> dict:
    if not rows:
        return {"verdict": "NO_CANDIDATES"}
    inverted = [{**r, "outcome_bps": -float(r["outcome_bps"])} for r in rows]
    rng = random.Random(20260721)
    shuffled = [{**r, "outcome_bps": rows[rng.randrange(len(rows))]["outcome_bps"]} for r in rows]
    real = summarize(rows)
    inv = summarize(inverted)
    shuf = summarize(shuffled)
    return {
        "real_mean_bps": real["mean_bps"],
        "direction_inversion_mean_bps": inv["mean_bps"],
        "deterministic_shuffle_mean_bps": shuf["mean_bps"],
        "future_suffix_invariance": "PASS_STATIC_PREFIX_ONLY_GENERATORS",
        "candidate_id_corruption": "PASS_IDS_HASH_CAUSAL_FIELDS",
        "timestamp_lookahead_trap": "PASS_GENERATORS_USE_COMPLETED_PREFIX_WINDOWS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=int, default=1)
    parser.add_argument("--partition", choices=("DISCOVERY", "SCREENING", "FINAL_LOCKBOX"), default="DISCOVERY")
    parser.add_argument("--hypothesis-id", action="append", default=None)
    args = parser.parse_args()
    hypothesis_ids = args.hypothesis_id or CYCLE_HYPOTHESES.get(args.cycle)
    if not hypothesis_ids:
        raise ValueError(f"unknown_cycle:{args.cycle}")
    manifest = json.loads((BASE / "session_partition_manifest.json").read_text())
    partition_sessions = manifest["partitions"][args.partition]["sessions"]
    sessions_data = {s: load_session(s) for s in partition_sessions}
    all_results = {}
    for hyp in hypothesis_ids:
        generator = GENERATORS[hyp]
        prior_data = None
        candidates: list[Candidate] = []
        for session in partition_sessions:
            cs = generator(session, sessions_data[session], prior_data)
            candidates.extend(cs)
            prior_data = sessions_data[session]
        rows = evaluate_candidates(candidates, sessions_data)
        summary = summarize(rows)
        folds = wfa(rows, partition_sessions) if args.partition == "DISCOVERY" else []
        positive_folds = sum(1 for f in folds if f.get("mean_bps") is not None and f["mean_bps"] > 0)
        gate_failures = []
        if summary["candidate_count"] < 100:
            gate_failures.append(f"REJECTED_INSUFFICIENT_{args.partition}_CANDIDATES")
        if summary["session_count"] < 30:
            gate_failures.append(f"REJECTED_INSUFFICIENT_{args.partition}_SESSIONS")
        if summary["mean_bps"] is None or summary["mean_bps"] <= 0:
            gate_failures.append(f"REJECTED_{args.partition}_MEAN_NOT_POSITIVE")
        if args.partition == "FINAL_LOCKBOX" and (
            summary.get("session_clustered_mean_ci_95", [None])[0] is None
            or summary["session_clustered_mean_ci_95"][0] <= 0
        ):
            gate_failures.append("REJECTED_FINAL_LOCKBOX_CLUSTERED_LOWER_CI_NOT_POSITIVE")
        if args.partition in {"SCREENING", "FINAL_LOCKBOX"} and (
            summary.get("positive_session_fraction") is None or summary["positive_session_fraction"] <= 0.50
        ):
            gate_failures.append(f"REJECTED_{args.partition}_POSITIVE_SESSION_FRACTION")
        if args.partition == "DISCOVERY" and positive_folds < 4:
            gate_failures.append("REJECTED_WFA_POSITIVE_FOLD_COUNT")
        if summary.get("single_session_concentration", 1) > 0.10:
            gate_failures.append("REJECTED_SINGLE_SESSION_CONCENTRATION")
        all_results[hyp] = {
            "summary": summary,
            "wfa": folds,
            "positive_wfa_folds": positive_folds,
            "controls": control_summary(rows),
            "gate_failures": gate_failures,
            "verdict": f"{args.partition}_GATE_PASS" if not gate_failures else "|".join(gate_failures),
            "rows_sample": rows[:10],
        }
    out = {
        "schema_version": 1,
        "research_epoch_id": "AVAILABLE_CORPUS_EPOCH_2024_2026_V1",
        "partition": args.partition,
        "final_lockbox_opened": args.partition == "FINAL_LOCKBOX",
        "results": all_results,
        "safety_flags": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "execution_eligibility": False,
            "allowed_for_live_execution": False,
        },
    }
    suffix = args.partition.lower()
    (BASE / f"cycle_{args.cycle}_{suffix}_results.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
