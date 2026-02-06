import json
import math
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict
from config import config as cfg


def _load_jsonl(path: str):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _trend_slope(values):
    if len(values) < 2:
        return 0.0
    return values[-1] - values[0]


def _rolling_stats(pnls):
    if not pnls:
        return {"exp": 0.0, "sharpe": 0.0, "hit_rate": 0.0}
    exp = sum(pnls) / len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    hit = wins / len(pnls)
    mean = exp
    var = sum((p - mean) ** 2 for p in pnls) / max(1, len(pnls))
    std = math.sqrt(var)
    sharpe = mean / std if std > 0 else 0.0
    return {"exp": exp, "sharpe": sharpe, "hit_rate": hit}


def _psi(dist_a, dist_b):
    # simple PSI on category distributions
    keys = set(dist_a.keys()) | set(dist_b.keys())
    psi = 0.0
    for k in keys:
        a = max(dist_a.get(k, 1e-6), 1e-6)
        b = max(dist_b.get(k, 1e-6), 1e-6)
        psi += (a - b) * math.log(a / b)
    return psi


def _feature_importance_instability():
    cur = Path("logs/feature_importance.csv")
    prev = Path("logs/feature_importance_prev.csv")
    if not cur.exists():
        return 0.0
    if not prev.exists():
        prev.write_text(cur.read_text())
        return 0.0
    try:
        import pandas as pd
        cur_df = pd.read_csv(cur)
        prev_df = pd.read_csv(prev)
        if cur_df.empty or prev_df.empty:
            return 0.0
        cur_rank = {r["feature"]: i for i, r in cur_df.sort_values("importance", ascending=False).iterrows()}
        prev_rank = {r["feature"]: i for i, r in prev_df.sort_values("importance", ascending=False).iterrows()}
        common = set(cur_rank.keys()) & set(prev_rank.keys())
        if not common:
            return 0.0
        diffs = [abs(cur_rank[f] - prev_rank[f]) for f in common]
        instability = sum(diffs) / max(len(diffs), 1)
        prev.write_text(cur.read_text())
        return float(instability)
    except Exception:
        return 0.0


def compute_decay(tracker, risk_state=None, window=50):
    trade_log = _load_jsonl("data/trade_log.json")
    updates = _load_jsonl("data/trade_updates.json")
    upd_map = {u.get("trade_id"): u for u in updates if u.get("type") == "outcome"}

    by_strategy = defaultdict(list)
    by_regime = defaultdict(list)
    slippage_by_strategy = defaultdict(list)

    for t in trade_log:
        tid = t.get("trade_id")
        strat = t.get("strategy")
        if not strat:
            continue
        out = upd_map.get(tid)
        if not out:
            continue
        entry = _safe_float(t.get("entry"), 0.0)
        exit_price = _safe_float(out.get("exit_price"), entry)
        qty = _safe_float(t.get("qty"), 1.0)
        side = t.get("side", "BUY")
        pnl = (exit_price - entry) * qty
        if side == "SELL":
            pnl *= -1
        by_strategy[strat].append(pnl)
        by_regime[strat].append(t.get("regime", "UNKNOWN"))
        slippage = _safe_float(t.get("slippage"), 0.0)
        slippage_by_strategy[strat].append(slippage)

    fill_quality = _load_jsonl("logs/fill_quality.jsonl")
    fill_by_strategy = defaultdict(list)
    if fill_quality:
        # Map trade_id -> strategy
        trade_map = {t.get("trade_id"): t.get("strategy") for t in trade_log}
        for fq in fill_quality:
            strat = trade_map.get(fq.get("trade_id"))
            if not strat:
                continue
            filled = 1.0 if fq.get("filled") else 0.0
            fill_by_strategy[strat].append(filled)

    model_health = {}
    try:
        mh_path = Path("logs/model_health.json")
        if mh_path.exists():
            model_health = json.loads(mh_path.read_text())
    except Exception:
        model_health = {}

    cross_asset = {}
    try:
        ca_path = Path("logs/cross_asset_features.json")
        if ca_path.exists():
            cross_asset = json.loads(ca_path.read_text())
    except Exception:
        cross_asset = {}

    decay_out = {}
    instability = _feature_importance_instability()

    for strat, pnls in by_strategy.items():
        recent = pnls[-window:]
        prev = pnls[-2 * window:-window] if len(pnls) >= 2 * window else []
        r_stats = _rolling_stats(recent)
        p_stats = _rolling_stats(prev)
        sharpe_slope = r_stats["sharpe"] - p_stats["sharpe"]
        hit_drift = r_stats["hit_rate"] - p_stats["hit_rate"]
        exp_roll = r_stats["exp"]
        sharpe_decay = -sharpe_slope
        fill_recent = fill_by_strategy[strat][-window:] if fill_by_strategy[strat] else []
        fill_prev = fill_by_strategy[strat][-2 * window:-window] if fill_by_strategy[strat] else []
        fill_decay = (sum(fill_prev) / max(len(fill_prev), 1)) - (sum(fill_recent) / max(len(fill_recent), 1))
        slip_recent = slippage_by_strategy[strat][-window:] if slippage_by_strategy[strat] else []
        slip_prev = slippage_by_strategy[strat][-2 * window:-window] if slippage_by_strategy[strat] else []
        slippage_trend = (sum(slip_recent) / max(len(slip_recent), 1)) - (sum(slip_prev) / max(len(slip_prev), 1))

        reg_recent = by_regime[strat][-window:] if by_regime[strat] else []
        reg_prev = by_regime[strat][-2 * window:-window] if by_regime[strat] else []
        def dist(xs):
            d = defaultdict(int)
            for x in xs:
                d[x] += 1
            total = max(len(xs), 1)
            return {k: v / total for k, v in d.items()}
        regime_shift = _psi(dist(reg_recent), dist(reg_prev)) if reg_recent and reg_prev else 0.0

        psi = _safe_float(model_health.get("psi"), 0.0)
        ks = _safe_float(model_health.get("ks"), 0.0)

        weights = getattr(cfg, "DECAY_WEIGHTS", {
            "exp": -0.6,
            "sharpe_decay": 0.8,
            "hit_drift": -0.5,
            "fill_decay": 0.6,
            "slippage_trend": 0.4,
            "regime_shift": 0.6,
            "psi": 0.7,
            "ks": 0.4,
            "importance_instability": 0.3,
            "cross_align": 0.2,
            "cross_volspill": 0.2,
        })

        x_align = _safe_float(cross_asset.get("x_regime_align"), 0.0)
        x_volspill = _safe_float(cross_asset.get("x_vol_spillover"), 0.0)
        cross_align_pen = -x_align
        cross_vol_pen = max(0.0, x_volspill - 1.0)

        score = (
            weights["exp"] * exp_roll +
            weights["sharpe_decay"] * sharpe_decay +
            weights["hit_drift"] * (-hit_drift) +
            weights["fill_decay"] * fill_decay +
            weights["slippage_trend"] * slippage_trend +
            weights["regime_shift"] * regime_shift +
            weights["psi"] * psi +
            weights["ks"] * ks +
            weights["importance_instability"] * instability +
            weights["cross_align"] * cross_align_pen +
            weights["cross_volspill"] * cross_vol_pen
        )
        decay_prob = _sigmoid(score)

        decay_out[strat] = {
            "decay_probability": round(decay_prob, 4),
            "rolling_expectancy": round(exp_roll, 4),
            "sharpe_decay": round(sharpe_decay, 4),
            "hit_rate_drift": round(hit_drift, 4),
            "fill_decay": round(fill_decay, 4),
            "slippage_trend": round(slippage_trend, 4),
            "regime_shift": round(regime_shift, 4),
            "psi": round(psi, 4),
            "ks": round(ks, 4),
            "importance_instability": round(instability, 4),
            "cross_asset_align": round(x_align, 4),
            "cross_asset_volspill": round(x_volspill, 4),
        }

    # Time-to-failure estimate using history slope
    hist_path = Path("logs/strategy_decay_history.jsonl")
    history = _load_jsonl(str(hist_path))
    for strat, info in decay_out.items():
        past = [h for h in history if h.get("strategy") == strat]
        if len(past) >= 2:
            slope = past[-1]["decay_probability"] - past[0]["decay_probability"]
            slope = slope / max(len(past) - 1, 1)
        else:
            slope = 0.0
        threshold = float(getattr(cfg, "DECAY_PROB_THRESHOLD", 0.7))
        if slope <= 0:
            ttf = None
        else:
            ttf = max(0.0, (threshold - info["decay_probability"]) / slope)
        info["time_to_failure"] = ttf
        info["quarantine_recommendation"] = info["decay_probability"] >= threshold

        # append history
        hist_path.parent.mkdir(exist_ok=True)
        with hist_path.open("a") as f:
            f.write(json.dumps({
                "timestamp": str(datetime.now()),
                "strategy": strat,
                "decay_probability": info["decay_probability"],
                "time_to_failure": ttf,
            }) + "\n")

    # persist summary
    Path("logs").mkdir(exist_ok=True)
    Path("logs/strategy_decay.json").write_text(json.dumps(decay_out, indent=2))
    return decay_out
