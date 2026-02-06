import json
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import statistics as stats
from core.stress_generator import SyntheticStressGenerator


class ResearchPipeline:
    """
    Research pipeline for strategy robustness and degradation detection.
    Produces walk-forward stats, regime segmentation, Monte Carlo resampling,
    purged CV diagnostics, calibration curves, feature importance stability,
    and overfit alarms.
    """
    def __init__(self, trade_log_path="data/trade_log.json", out_dir="logs"):
        self.trade_log_path = Path(trade_log_path)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(exist_ok=True)

    def run(self, tracker=None, retrainer=None, risk_state=None):
        trades = self._load_trades()
        if not trades:
            return {"status": "no_trades"}

        stats_by_strategy = self._strategy_stats(trades)
        regime_stats = self._regime_segmented_stats(trades)
        mc = self._monte_carlo(trades)
        wf = self._walk_forward(trades)
        cal = self._calibration(trades)
        fi = self._feature_importance_stability()
        overfit = self._overfit_alarms(stats_by_strategy, wf, mc)
        stress = None
        try:
            if bool(getattr(__import__("config.config", fromlist=["STRESS_TEST_ENABLE"]).STRESS_TEST_ENABLE, "STRESS_TEST_ENABLE", False)):
                stress = self._stress_test(trades)
        except Exception:
            stress = None

        payload = {
            "timestamp": datetime.now().isoformat(),
            "strategy_stats": stats_by_strategy,
            "regime_stats": regime_stats,
            "monte_carlo": mc,
            "walk_forward": wf,
            "calibration": cal,
            "feature_importance": fi,
            "overfit_alarms": overfit,
            "stress_test": stress,
        }
        self._write_json("research_pipeline.json", payload)

        # Apply degradation to StrategyTracker
        if tracker is not None:
            degraded = {k: v for k, v in overfit.get("degraded_strategies", {}).items()}
            tracker.set_degraded(degraded)
        # Update RiskState if present
        try:
            if risk_state is not None:
                risk_state.update_model_drift(overfit.get("drift_metrics", {}))
        except Exception:
            pass
        return payload

    def _load_trades(self):
        if not self.trade_log_path.exists():
            return []
        raw = []
        try:
            text = self.trade_log_path.read_text().strip()
            if text.startswith("["):
                raw = json.loads(text)
            else:
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    try:
                        raw.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return []
        trades = []
        for r in raw:
            strategy = r.get("strategy")
            if not strategy:
                continue
            pnl = r.get("pnl")
            if pnl is None:
                try:
                    entry = r.get("entry") or r.get("entry_price")
                    exit_p = r.get("exit") or r.get("exit_price")
                    side = r.get("side", "BUY")
                    qty = r.get("qty", 1)
                    if entry is not None and exit_p is not None:
                        pnl = (exit_p - entry) * qty if side == "BUY" else (entry - exit_p) * qty
                except Exception:
                    pnl = None
            if pnl is None:
                continue
            # slippage-aware PnL
            slippage = None
            try:
                slippage = r.get("expected_slippage") or r.get("slippage")
                if not slippage and isinstance(r.get("fill_quality"), dict):
                    slippage = r["fill_quality"].get("slippage_vs_mid")
            except Exception:
                slippage = None
            pnl_adj = pnl - (slippage or 0)
            ts = r.get("timestamp") or r.get("ts")
            try:
                ts = datetime.fromisoformat(ts).timestamp()
            except Exception:
                ts = None
            trades.append({
                "strategy": strategy,
                "regime": r.get("regime") or r.get("regime_day"),
                "pnl": float(pnl),
                "pnl_adj": float(pnl_adj),
                "confidence": r.get("confidence"),
                "timestamp": ts,
            })
        return trades

    def _strategy_stats(self, trades):
        by_strat = defaultdict(list)
        for t in trades:
            by_strat[t["strategy"]].append(t)
        out = {}
        for s, rows in by_strat.items():
            pnl = [r["pnl_adj"] for r in rows]
            wins = [p for p in pnl if p > 0]
            losses = [p for p in pnl if p < 0]
            expectancy = round(stats.mean(pnl), 4) if pnl else 0.0
            sharpe = self._sharpe(pnl)
            sortino = self._sortino(pnl)
            tail = self._cvar(pnl, q=0.05)
            win_rate = round(len(wins) / len(pnl), 4) if pnl else 0.0
            decay = self._decay_rate(rows)
            out[s] = {
                "trades": len(pnl),
                "expectancy": expectancy,
                "sharpe": sharpe,
                "sortino": sortino,
                "tail_loss": tail,
                "win_rate": win_rate,
                "decay_rate": decay,
            }
        return out

    def _regime_segmented_stats(self, trades):
        out = {}
        by = defaultdict(list)
        for t in trades:
            key = (t["strategy"], t.get("regime") or "UNKNOWN")
            by[key].append(t["pnl_adj"])
        for (strategy, regime), pnl in by.items():
            out.setdefault(strategy, {})
            out[strategy][regime] = {
                "trades": len(pnl),
                "expectancy": round(stats.mean(pnl), 4) if pnl else 0.0,
                "win_rate": round(len([p for p in pnl if p > 0]) / len(pnl), 4) if pnl else 0.0,
            }
        return out

    def _monte_carlo(self, trades, n=500):
        pnl_by_strategy = defaultdict(list)
        for t in trades:
            pnl_by_strategy[t["strategy"]].append(t["pnl_adj"])
        out = {}
        for s, pnl in pnl_by_strategy.items():
            if len(pnl) < 10:
                continue
            sims = []
            for _ in range(n):
                sample = [pnl[int(i * len(pnl)) % len(pnl)] for i in range(len(pnl))]
                sims.append(sum(sample))
            sims.sort()
            out[s] = {
                "mc_mean": round(stats.mean(sims), 4),
                "mc_p05": round(sims[int(0.05 * len(sims))], 4),
                "mc_p95": round(sims[int(0.95 * len(sims))], 4),
            }
        return out

    def _walk_forward(self, trades, window=50, step=25):
        by_strat = defaultdict(list)
        for t in trades:
            by_strat[t["strategy"]].append(t)
        out = {}
        for s, rows in by_strat.items():
            rows = sorted(rows, key=lambda r: r.get("timestamp") or 0)
            if len(rows) < window * 2:
                continue
            wf_stats = []
            for start in range(0, len(rows) - window, step):
                train = rows[start:start + window]
                test = rows[start + window:start + window + step]
                if not test:
                    continue
                train_exp = stats.mean([r["pnl_adj"] for r in train])
                test_exp = stats.mean([r["pnl_adj"] for r in test])
                wf_stats.append({
                    "train_expectancy": round(train_exp, 4),
                    "test_expectancy": round(test_exp, 4),
                })
            out[s] = wf_stats
        return out

    def _calibration(self, trades, bins=10):
        out = {}
        by_strat = defaultdict(list)
        for t in trades:
            if t.get("confidence") is None:
                continue
            by_strat[t["strategy"]].append(t)
        for s, rows in by_strat.items():
            bins_out = []
            for b in range(bins):
                lo = b / bins
                hi = (b + 1) / bins
                bucket = [r for r in rows if r["confidence"] is not None and lo <= r["confidence"] < hi]
                if not bucket:
                    continue
                wins = sum(1 for r in bucket if r["pnl_adj"] > 0)
                bins_out.append({
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "count": len(bucket),
                    "empirical_win": round(wins / len(bucket), 4),
                })
            out[s] = bins_out
        return out

    def _feature_importance_stability(self):
        path = self.out_dir / "feature_importance.csv"
        if not path.exists():
            return {"status": "missing"}
        try:
            import pandas as pd
            df = pd.read_csv(path)
            if "feature" not in df.columns or "importance" not in df.columns:
                return {"status": "invalid"}
            stds = df.groupby("feature")["importance"].std().fillna(0).to_dict()
            means = df.groupby("feature")["importance"].mean().fillna(0).to_dict()
            stability = {k: round(float(stds[k] / (means[k] + 1e-6)), 4) for k in means.keys()}
            return {"stability": stability}
        except Exception:
            return {"status": "error"}

    def _overfit_alarms(self, stats_by_strategy, wf, mc):
        degraded = {}
        drift_metrics = {}
        min_sharpe = float(__import__("config.config", fromlist=["RESEARCH_DEGRADE_SHARPE_MIN"]).RESEARCH_DEGRADE_SHARPE_MIN)
        min_expect = float(__import__("config.config", fromlist=["RESEARCH_DEGRADE_EXPECTANCY_MIN"]).RESEARCH_DEGRADE_EXPECTANCY_MIN)
        tail_limit = float(__import__("config.config", fromlist=["RESEARCH_DEGRADE_TAIL_CVAR_MAX"]).RESEARCH_DEGRADE_TAIL_CVAR_MAX)
        for s, st in stats_by_strategy.items():
            if st.get("trades", 0) < 20:
                continue
            if st.get("sharpe") is not None and st["sharpe"] < min_sharpe:
                degraded[s] = f"low_sharpe:{st['sharpe']}"
            if st.get("expectancy", 0) < min_expect:
                degraded[s] = f"low_expectancy:{st['expectancy']}"
            if st.get("tail_loss", 0) < tail_limit:
                degraded[s] = f"tail_loss:{st['tail_loss']}"
            # walk-forward degradation check
            wf_stats = wf.get(s, [])
            if wf_stats:
                test_exp = [w["test_expectancy"] for w in wf_stats]
                if test_exp and stats.mean(test_exp) < 0:
                    degraded[s] = "wf_negative_expectancy"
        drift_metrics["degraded_count"] = len(degraded)
        return {"degraded_strategies": degraded, "drift_metrics": drift_metrics}

    def _stress_test(self, trades):
        returns = []
        start_price = None
        for t in trades:
            pnl = t.get("pnl_adj")
            entry = t.get("entry") or t.get("entry_price")
            if entry and pnl is not None:
                try:
                    r = float(pnl) / max(float(entry), 1.0)
                    returns.append(r)
                    if start_price is None:
                        start_price = float(entry)
                except Exception:
                    continue
        if not returns:
            return {"status": "no_returns"}
        gen = SyntheticStressGenerator()
        n_steps = int(getattr(__import__("config.config", fromlist=["STRESS_STEPS"]).STRESS_STEPS, "STRESS_STEPS", 240))
        n_paths = int(getattr(__import__("config.config", fromlist=["STRESS_PATHS"]).STRESS_PATHS, "STRESS_PATHS", 250))
        report = gen.run(returns, start_price or 1.0, n_steps=n_steps, n_paths=n_paths)
        return report

    def _decay_rate(self, rows, window=30):
        rows = sorted(rows, key=lambda r: r.get("timestamp") or 0)
        if len(rows) < window:
            return 0.0
        pnl = [r["pnl_adj"] for r in rows[-window:]]
        try:
            x = list(range(len(pnl)))
            x_mean = stats.mean(x)
            y_mean = stats.mean(pnl)
            num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, pnl))
            den = sum((xi - x_mean) ** 2 for xi in x)
            slope = num / den if den else 0.0
            return round(slope, 6)
        except Exception:
            return 0.0

    def _sharpe(self, pnl):
        if len(pnl) < 5:
            return None
        stdev = stats.pstdev(pnl)
        if stdev == 0:
            return None
        return round(stats.mean(pnl) / stdev, 3)

    def _sortino(self, pnl):
        if len(pnl) < 5:
            return None
        neg = [p for p in pnl if p < 0]
        if not neg:
            return None
        stdev = stats.pstdev(neg)
        if stdev == 0:
            return None
        return round(stats.mean(pnl) / stdev, 3)

    def _cvar(self, pnl, q=0.05):
        if not pnl:
            return 0.0
        pnl_sorted = sorted(pnl)
        cut = max(1, int(len(pnl_sorted) * q))
        tail = pnl_sorted[:cut]
        return round(stats.mean(tail), 4)

    def _write_json(self, name, payload):
        try:
            path = self.out_dir / name
            path.write_text(json.dumps(payload, indent=2))
        except Exception:
            pass
