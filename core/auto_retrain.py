# Migration note:
# Auto-retrain now ensures canonical trade-log path exists and returns structured skip reasons.

import json
import time
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

from config import config as cfg
from ml.trade_predictor import TradePredictor
from core.model_health import ModelHealth
from core.research_pipeline import ResearchPipeline
from core import model_registry
from core import ml_governance
from core.strategy_decay import compute_decay
from core.retrain_manager import RetrainManager
from core.trade_log_paths import ensure_trade_log_exists, ensure_trade_log_file, resolve_trade_log_path


class AutoRetrain:
    def __init__(self, predictor: TradePredictor, model_path=None, risk_state=None, strategy_tracker=None):
        self.predictor = predictor
        self.model_path = model_path or getattr(cfg, "ML_MODEL_PATH", "models/xgb_live_model.pkl")
        self.challenger_path = getattr(cfg, "ML_CHALLENGER_MODEL_PATH", "models/xgb_live_model_challenger.pkl")
        self.baseline_path = Path(getattr(cfg, "ML_DRIFT_BASELINE_PATH", "logs/drift_baseline.json"))
        self.decision_path = Path(getattr(cfg, "ML_MODEL_DECISIONS_PATH", "logs/model_decisions.jsonl"))
        self.health_checker = ModelHealth()
        self.risk_state = risk_state
        self.strategy_tracker = strategy_tracker
        self.research = ResearchPipeline()
        self.segment_cols = ["seg_regime", "seg_bucket", "seg_expiry", "seg_vol_q"]
        self.retrain_manager = RetrainManager()

    def update_model(self, trade_log_path=None):
        resolved_log_path = (
            ensure_trade_log_file(trade_log_path, create_if_missing=True)
            if trade_log_path is not None
            else ensure_trade_log_exists()
        )
        live_df = self._load_trade_log(resolved_log_path)
        if live_df is None or live_df.empty:
            print(f"[AutoRetrain] Trade log not found/unreadable/empty: {resolved_log_path}")
            try:
                self.research.run(tracker=self.strategy_tracker, retrainer=self, risk_state=self.risk_state)
            except Exception:
                pass
            try:
                decay = compute_decay(self.strategy_tracker, self.risk_state, window=getattr(cfg, "DECAY_WINDOW_TRADES", 50))
                self.strategy_tracker.set_decay(decay)
                if self.risk_state:
                    for strat, info in decay.items():
                        if info.get("decay_probability", 0) >= float(getattr(cfg, "DECAY_PROB_THRESHOLD", 0.7)):
                            self.risk_state.quarantine_strategy(strat, reason="strategy_decay")
            except Exception:
                pass
            return {"status": "skipped", "reason": "trade_log_missing_or_empty", "path": str(resolved_log_path)}

        drift = self._compute_drift(live_df)
        try:
            if self.risk_state is not None:
                self.risk_state.update_model_drift(drift)
        except Exception:
            pass
        try:
            active_path = model_registry.get_active("xgb")
            if active_path:
                model_registry.update_model_metrics("xgb", active_path, governance={"drift": drift})
        except Exception:
            pass
        try:
            self._maybe_rollback(drift)
        except Exception:
            pass
        trigger = self.retrain_manager.evaluate_retrain_trigger(live_df)
        if not trigger.retrain_required:
            self._log_decision(
                "skip",
                {
                    "reason": "retrain_not_required",
                    "retrain_required": False,
                    "retrain_reasons": trigger.reason_codes,
                    "rolling_metrics": trigger.metrics,
                },
            )
            return {"status": "skipped", "reason": "retrain_not_required"}

        # cooldown guard
        cooldown = getattr(cfg, "RETRAIN_COOLDOWN_MIN", 180) * 60
        state_path = Path("logs/last_retrain.json")
        last_ts = 0
        if state_path.exists():
            try:
                last_ts = json.loads(state_path.read_text()).get("ts", 0)
            except Exception:
                last_ts = 0
        if time.time() - last_ts < cooldown:
            self._log_decision("skip", {"reason": "cooldown", "cooldown_sec": cooldown})
            return {"status": "skipped", "reason": "cooldown"}

        # Train challenger
        train_df = self._load_training_dataset()
        if train_df is None or train_df.empty:
            self._log_decision("skip", {"reason": "no_train_data"})
            return {"status": "skipped", "reason": "no_train_data"}

        train_df = self._add_segments_train(train_df)
        baseline = self._load_or_init_baseline(live_df)
        drift_ok, drift_reasons = self._should_retrain(live_df, drift)
        expect_ok, expect_detail = self._expectancy_below_baseline(live_df, baseline)
        seg_ok, seg_detail = self._segments_ok(train_df)
        if not (drift_ok and expect_ok and seg_ok):
            self._log_decision("skip", {
                "reason": "gates_not_met",
                "retrain_required": True,
                "trigger_reasons": trigger.reason_codes,
                "rolling_metrics": trigger.metrics,
                "drift": drift_reasons,
                "expectancy": expect_detail,
                "segments": seg_detail,
            })
            try:
                self.research.run(tracker=self.strategy_tracker, retrainer=self, risk_state=self.risk_state)
            except Exception:
                pass
            try:
                decay = compute_decay(self.strategy_tracker, self.risk_state, window=getattr(cfg, "DECAY_WINDOW_TRADES", 50))
                self.strategy_tracker.set_decay(decay)
                if self.risk_state:
                    for strat, info in decay.items():
                        if info.get("decay_probability", 0) >= float(getattr(cfg, "DECAY_PROB_THRESHOLD", 0.7)):
                            self.risk_state.quarantine_strategy(strat, reason="strategy_decay")
            except Exception:
                pass
            return {"status": "skipped", "reason": "gates_not_met"}

        # Split holdout
        holdout_frac = float(getattr(cfg, "ML_HOLDOUT_FRAC", 0.2))
        train_df, holdout_df = self._split_holdout(train_df, holdout_frac)

        challenger = TradePredictor(model_path=self.challenger_path, load_existing=False)
        challenger.train_segmented(
            train_df,
            target_col=getattr(cfg, "ML_TRAIN_TARGET_COL", "target"),
            segment_cols=self.segment_cols,
            min_samples=getattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 200),
        )

        # Evaluate champion vs challenger (with statistical test)
        y, champ_preds = self._predict_on_df(
            self.predictor,
            holdout_df,
            target_col=getattr(cfg, "ML_TRAIN_TARGET_COL", "target"),
            segment_cols=self.segment_cols,
        )
        _, chall_preds = self._predict_on_df(
            challenger,
            holdout_df,
            target_col=getattr(cfg, "ML_TRAIN_TARGET_COL", "target"),
            segment_cols=self.segment_cols,
        )
        champ_metrics = _metrics_from_preds(y, champ_preds, pnl=holdout_df.get("pnl"))
        chall_metrics = _metrics_from_preds(y, chall_preds, pnl=holdout_df.get("pnl"))
        stat = ml_governance.bootstrap_pvalue(
            y,
            champ_preds,
            chall_preds,
            metric="brier",
            n=int(getattr(cfg, "ML_PROMOTE_BOOTSTRAP", 500)),
        )
        shadow_df = self._shadow_eval_df(train_df)
        champ_shadow = None
        chall_shadow = None
        if shadow_df is not None and not shadow_df.empty:
            y_s, champ_s = self._predict_on_df(
                self.predictor,
                shadow_df,
                target_col=getattr(cfg, "ML_TRAIN_TARGET_COL", "target"),
                segment_cols=self.segment_cols,
            )
            _, chall_s = self._predict_on_df(
                challenger,
                shadow_df,
                target_col=getattr(cfg, "ML_TRAIN_TARGET_COL", "target"),
                segment_cols=self.segment_cols,
            )
            champ_shadow = _metrics_from_preds(y_s, champ_s, pnl=shadow_df.get("pnl"))
            chall_shadow = _metrics_from_preds(y_s, chall_s, pnl=shadow_df.get("pnl"))

        promote, reason = self._should_promote(champ_metrics, chall_metrics, stat, champ_shadow, chall_shadow)
        promotion_gate = self.retrain_manager.evaluate_promotion_gate(
            champion_metrics=champ_metrics,
            challenger_metrics=chall_metrics,
        )
        if promote and not promotion_gate.allowed:
            promote = False
            reason = promotion_gate.reason_code
        elif promote and promotion_gate.allowed:
            reason = promotion_gate.reason_code
        elif not promote and promotion_gate.allowed:
            # Keep conservative gate behavior: core gate must pass first.
            reason = f"MODEL_PROMOTE_REJECT:CORE_GATE:{reason}"
        elif not promote and not promotion_gate.allowed and not str(reason).startswith("MODEL_PROMOTE_REJECT:"):
            reason = promotion_gate.reason_code
        decision = {
            "timestamp": datetime.now().isoformat(),
            "retrain_required": True,
            "trigger_reasons": trigger.reason_codes,
            "rolling_metrics": trigger.metrics,
            "retrain_reasons": drift_reasons,
            "champion": champ_metrics,
            "challenger": chall_metrics,
            "stat_test": stat,
            "shadow_champion": champ_shadow,
            "shadow_challenger": chall_shadow,
            "promote": promote,
            "reason": reason,
            "promotion_gate": promotion_gate.details,
        }

        # Governance metadata
        champ_cal = ml_governance.calibration_curve(champ_preds, y, bins=int(getattr(cfg, "ML_CALIBRATION_BINS", 10)))
        chall_cal = ml_governance.calibration_curve(chall_preds, y, bins=int(getattr(cfg, "ML_CALIBRATION_BINS", 10)))
        champ_gov = ml_governance.build_governance(
            train_df,
            feature_list=self.predictor.feature_list,
            regime_col="seg_regime",
            ts_col="timestamp",
            calibration=champ_cal,
            extra={"version_hash": ml_governance.file_hash(self.model_path)},
        )
        chall_gov = ml_governance.build_governance(
            train_df,
            feature_list=challenger.feature_list,
            regime_col="seg_regime",
            ts_col="timestamp",
            calibration=chall_cal,
            extra={"version_hash": ml_governance.file_hash(self.challenger_path)},
        )

        if promote:
            challenger.save(self.model_path)
            # Hot swap predictor in memory
            self.predictor.models = challenger.models
            self.predictor.feature_list = challenger.feature_list
            self.predictor.meta = challenger.meta
            model_registry.register_model("xgb", self.model_path, metrics=chall_metrics, governance=champ_gov, status="active")
            model_registry.activate_model("xgb", self.model_path, metrics=chall_metrics, governance=champ_gov)
            try:
                model_registry.prune_history("xgb", keep_n=int(getattr(cfg, "ML_ROLLBACK_KEEP_N", 3)))
            except Exception:
                pass
            try:
                active_entry = model_registry.get_active_entry("xgb")
                if active_entry:
                    self.predictor.model_version = active_entry.get("hash")
                    self.predictor.model_governance = active_entry.get("governance") or {}
            except Exception:
                pass
            try:
                self._write_model_metadata(self.model_path, champ_gov, extra={"metrics": chall_metrics, "shadow_eval": chall_shadow})
            except Exception:
                pass
            self._log_decision("promote", decision)
            state_path.parent.mkdir(exist_ok=True)
            state_path.write_text(json.dumps({"ts": time.time()}))
            print("[AutoRetrain] Challenger promoted and saved.")
        else:
            challenger.save(self.challenger_path)
            model_registry.register_model("xgb", self.challenger_path, metrics=chall_metrics, governance=chall_gov, status="shadow")
            model_registry.set_shadow("xgb", self.challenger_path, metrics=chall_metrics, governance=chall_gov)
            try:
                shadow_entry = model_registry.get_shadow_entry("xgb")
                if shadow_entry:
                    self.predictor.shadow_version = shadow_entry.get("hash")
                    self.predictor.shadow_governance = shadow_entry.get("governance") or {}
                    self.predictor.shadow_path = shadow_entry.get("path")
                    if self.predictor.shadow_path and Path(self.predictor.shadow_path).exists():
                        self.predictor._load_shadow(self.predictor.shadow_path)
            except Exception:
                pass
            try:
                self._write_model_metadata(self.challenger_path, chall_gov, extra={"metrics": chall_metrics, "shadow_eval": chall_shadow})
            except Exception:
                pass
            self._log_decision("shadow", decision)
            print("[AutoRetrain] Challenger did not beat champion; kept as shadow model.")

        try:
            self.research.run(tracker=self.strategy_tracker, retrainer=self, risk_state=self.risk_state)
        except Exception:
            pass
        try:
            decay = compute_decay(self.strategy_tracker, self.risk_state, window=getattr(cfg, "DECAY_WINDOW_TRADES", 50))
            self.strategy_tracker.set_decay(decay)
            if self.risk_state:
                for strat, info in decay.items():
                    if info.get("decay_probability", 0) >= float(getattr(cfg, "DECAY_PROB_THRESHOLD", 0.7)):
                        self.risk_state.quarantine_strategy(strat, reason="strategy_decay")
        except Exception:
            pass
        return {"status": "ok", "reason": "completed"}

    def _split_holdout(self, df, frac):
        if df.empty:
            return df, df
        frac = max(0.05, min(0.5, frac))
        idx = int(len(df) * (1 - frac))
        df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        return df.iloc[:idx].copy(), df.iloc[idx:].copy()

    def _load_training_dataset(self):
        path = getattr(cfg, "ML_TRAIN_DATA_PATH", "data/ml_features.csv")
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        try:
            df = pd.read_csv(p)
        except Exception:
            return None
        target_col = getattr(cfg, "ML_TRAIN_TARGET_COL", "target")
        if target_col not in df.columns:
            return None
        return df.dropna().reset_index(drop=True)

    def _load_trade_log(self, path):
        p = resolve_trade_log_path(path)
        if not p.exists():
            return None
        rows = []
        try:
            text = p.read_text().strip()
            if text.startswith("["):
                data = json.loads(text)
            else:
                data = [json.loads(line) for line in text.splitlines() if line.strip()]
        except Exception:
            return None

        for r in data:
            actual = r.get("actual")
            if actual is None:
                continue
            entry = r.get("entry") or r.get("entry_price")
            stop = r.get("stop_loss") or r.get("stop")
            target = r.get("target")
            side = (r.get("side") or "BUY").upper()
            exit_price = r.get("exit_price") or r.get("exit")
            conf = r.get("confidence")
            cap = r.get("capital_at_risk")
            ts = r.get("timestamp") or r.get("ts")
            try:
                ts = datetime.fromisoformat(str(ts))
            except Exception:
                ts = None

            pnl = None
            if entry is not None and exit_price is not None:
                try:
                    pnl = (exit_price - entry)
                    if side == "SELL":
                        pnl *= -1
                except Exception:
                    pnl = None

            rr = None
            try:
                if entry is not None and stop is not None and target is not None:
                    risk = abs(entry - stop)
                    reward = abs(target - entry)
                    rr = reward / risk if risk > 0 else None
            except Exception:
                rr = None

            rows.append({
                "confidence": conf,
                "entry": entry,
                "stop_loss": stop,
                "target": target,
                "rr": rr,
                "capital_at_risk": cap,
                "actual": int(actual),
                "predicted": r.get("predicted"),
                "pnl": pnl,
                "regime": r.get("regime") or r.get("day_type") or "UNKNOWN",
                "day_type": r.get("day_type") or "UNKNOWN",
                "timestamp": ts,
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df = self._add_segments_live(df)
        return df

    def _add_segments_live(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # time bucket
        def _bucket(ts):
            if ts is None or not hasattr(ts, "hour"):
                return "MID"
            h = ts.hour
            if h < 11:
                return "OPEN"
            if h < 14:
                return "MID"
            return "CLOSE"

        df["seg_bucket"] = df["timestamp"].apply(_bucket)
        # expiry
        df["seg_expiry"] = df["day_type"].astype(str).str.contains("EXPIRY", case=False, na=False).astype(int)
        # regime
        df["seg_regime"] = df["regime"].astype(str).str.upper().replace({"PANIC_DAY": "PANIC", "TREND_DAY": "TREND", "RANGE_DAY": "RANGE"})
        # vol quartile (fallback to confidence quartile)
        if "vol_z" in df.columns:
            src = df["vol_z"].fillna(0)
        else:
            src = df["confidence"].fillna(0)
        try:
            df["seg_vol_q"] = pd.qcut(src, 4, labels=[1, 2, 3, 4]).astype(int)
        except Exception:
            df["seg_vol_q"] = 2
        return df

    def _add_segments_train(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Regime inference using vwap_slope and vol_z
        def _infer_regime(row):
            try:
                vwap_slope = float(row.get("vwap_slope", 0) or 0)
                vol_z = float(row.get("vol_z", 0) or 0)
            except Exception:
                vwap_slope = 0
                vol_z = 0
            if abs(vwap_slope) > float(getattr(cfg, "REGIME_TREND_VWAP_SLOPE", 0.002)):
                return "TREND"
            if vol_z >= float(getattr(cfg, "REGIME_VOL_Z_RANGE_VOL", 1.0)):
                return "RANGE_VOLATILE"
            return "RANGE"

        if "seg_regime" not in df.columns:
            df["seg_regime"] = df.apply(_infer_regime, axis=1)
        if "seg_bucket" not in df.columns:
            df["seg_bucket"] = "MID"
        if "seg_expiry" not in df.columns:
            df["seg_expiry"] = 0
        if "seg_vol_q" not in df.columns:
            if "vol_z" in df.columns:
                try:
                    df["seg_vol_q"] = pd.qcut(df["vol_z"], 4, labels=[1, 2, 3, 4]).astype(int)
                except Exception:
                    df["seg_vol_q"] = 2
            else:
                df["seg_vol_q"] = 2
        return df

    def _compute_drift(self, live_df: pd.DataFrame):
        window = int(getattr(cfg, "ML_DRIFT_WINDOW", 200))
        live = live_df.tail(window).copy()
        baseline = self._load_or_init_baseline(live_df)

        feature_cols = [c for c in [
            "confidence", "entry", "stop_loss", "target", "rr", "capital_at_risk",
            "fx_ret_5m", "vix_z", "crude_ret_15m", "corr_fx_nifty",
            "x_usdinr_ret5", "x_india_vix_z", "x_crude_ret15", "x_usdinr_corr_nifty"
        ] if c in live.columns]
        drift = {
            "timestamp": datetime.now().isoformat(),
            "features": {},
            "psi_max": 0.0,
            "ks_max": 0.0,
            "target_drift": None,
            "calibration_error": None,
            "calibration_baseline": baseline.get("calibration"),
            "sharpe_live": None,
            "sharpe_baseline": baseline.get("sharpe"),
            "regime_shift_psi": None,
            "execution_quality_avg": None,
        }

        for col in feature_cols:
            exp = baseline.get("features", {}).get(col, {})
            exp_vals = exp.get("values")
            if exp_vals is None:
                exp_vals = live_df[col].dropna().values
            act_vals = live[col].dropna().values
            if len(exp_vals) < 10 or len(act_vals) < 5:
                continue
            psi = _psi(exp_vals, act_vals)
            ks = _ks(exp_vals, act_vals)
            drift["features"][col] = {"psi": psi, "ks": ks}
            drift["psi_max"] = max(drift["psi_max"], psi)
            drift["ks_max"] = max(drift["ks_max"], ks)

        # target drift (win rate)
        try:
            base_win = baseline.get("target_rate")
            live_win = float(live["actual"].mean()) if not live.empty else None
            drift["target_drift"] = (live_win - base_win) if (base_win is not None and live_win is not None) else None
        except Exception:
            drift["target_drift"] = None

        # calibration error (Brier)
        try:
            conf = live["confidence"].astype(float).clip(0, 1)
            actual = live["actual"].astype(float)
            brier = float(np.mean((conf - actual) ** 2)) if not live.empty else None
            drift["calibration_error"] = brier
        except Exception:
            drift["calibration_error"] = None

        # sharpe (from pnl)
        try:
            pnl = live["pnl"].dropna().values
            if len(pnl) >= 5:
                drift["sharpe_live"] = _sharpe(pnl)
        except Exception:
            drift["sharpe_live"] = None

        # regime distribution shift
        try:
            base_reg = baseline.get("regime_dist", {})
            live_reg = live["seg_regime"].value_counts(normalize=True).to_dict()
            drift["regime_shift_psi"] = _psi_from_dist(base_reg, live_reg)
        except Exception:
            drift["regime_shift_psi"] = None

        # execution quality (from daily fill quality)
        try:
            fq_path = Path("logs/fill_quality_daily.json")
            if fq_path.exists():
                fq = json.loads(fq_path.read_text())
                if fq:
                    latest = sorted(fq.keys())[-1]
                    drift["execution_quality_avg"] = fq.get(latest, {}).get("avg_exec_quality")
        except Exception:
            drift["execution_quality_avg"] = None

        # Persist drift metrics
        try:
            Path("logs").mkdir(exist_ok=True)
            with open("logs/drift_metrics.jsonl", "a") as f:
                f.write(json.dumps(drift) + "\n")
        except Exception:
            pass

        return drift

    def _should_retrain(self, live_df: pd.DataFrame, drift: dict):
        triggers = {}
        psi_thr = float(getattr(cfg, "ML_PSI_THRESHOLD", 0.2))
        ks_thr = float(getattr(cfg, "ML_KS_THRESHOLD", 0.2))
        cal_delta = float(getattr(cfg, "ML_CALIBRATION_DELTA", 0.05))

        if drift.get("psi_max") is not None and drift.get("psi_max") > psi_thr:
            triggers["psi"] = drift.get("psi_max")
        if drift.get("ks_max") is not None and drift.get("ks_max") > ks_thr:
            triggers["ks"] = drift.get("ks_max")
        # calibration error delta
        try:
            if drift.get("calibration_error") is not None and drift.get("calibration_baseline") is not None:
                if (drift["calibration_error"] - drift["calibration_baseline"]) > cal_delta:
                    triggers["calibration"] = drift["calibration_error"]
        except Exception:
            pass
        return (len(triggers) > 0), triggers

    def _load_or_init_baseline(self, df: pd.DataFrame):
        if self.baseline_path.exists():
            try:
                return json.loads(self.baseline_path.read_text())
            except Exception:
                pass

        baseline = self._build_baseline(df)
        try:
            self.baseline_path.parent.mkdir(exist_ok=True)
            self.baseline_path.write_text(json.dumps(baseline, indent=2))
        except Exception:
            pass
        return baseline

    def _build_baseline(self, df: pd.DataFrame):
        feature_cols = [c for c in [
            "confidence", "entry", "stop_loss", "target", "rr", "capital_at_risk",
            "fx_ret_5m", "vix_z", "crude_ret_15m", "corr_fx_nifty",
            "x_usdinr_ret5", "x_india_vix_z", "x_crude_ret15", "x_usdinr_corr_nifty"
        ] if c in df.columns]
        features = {}
        for col in feature_cols:
            vals = df[col].dropna().values
            if len(vals) < 10:
                continue
            features[col] = {
                "values": vals.tolist(),
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
            }
        conf = df["confidence"].astype(float).clip(0, 1)
        actual = df["actual"].astype(float)
        brier = float(np.mean((conf - actual) ** 2)) if len(df) else None
        pnl = df["pnl"].dropna().values
        sharpe = _sharpe(pnl) if len(pnl) >= 5 else None
        expectancy = float(np.mean(pnl)) if len(pnl) else None
        regime_dist = df["seg_regime"].value_counts(normalize=True).to_dict() if "seg_regime" in df.columns else {}
        return {
            "timestamp": datetime.now().isoformat(),
            "features": features,
            "target_rate": float(df["actual"].mean()) if not df.empty else None,
            "calibration": brier,
            "sharpe": sharpe,
            "expectancy": expectancy,
            "regime_dist": regime_dist,
        }

    def _segments_ok(self, df: pd.DataFrame):
        if df is None or df.empty:
            return False, {"reason": "empty_train"}
        for col in self.segment_cols:
            if col not in df.columns:
                return False, {"reason": "missing_segment_cols", "missing": col}
        min_samples = int(getattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 200))
        counts = df.groupby(self.segment_cols).size().reset_index(name="count")
        low = counts[counts["count"] < min_samples]
        if not low.empty:
            return False, {
                "reason": "segment_under_min",
                "min_samples": min_samples,
                "segments": low.to_dict(orient="records"),
            }
        return True, {"min_samples": min_samples, "segments": int(len(counts))}

    def _expectancy_below_baseline(self, live_df: pd.DataFrame, baseline: dict):
        baseline_exp = baseline.get("expectancy")
        if baseline_exp is None:
            return False, {"reason": "baseline_missing"}
        if live_df is None or live_df.empty or "pnl" not in live_df.columns:
            return False, {"reason": "no_live_pnl"}
        pnl = live_df["pnl"].dropna().values
        window = int(getattr(cfg, "ML_EXPECTANCY_WINDOW", 50))
        min_windows = int(getattr(cfg, "ML_EXPECTANCY_MIN_WINDOWS", 3))
        if window <= 0 or min_windows <= 0:
            return False, {"reason": "invalid_window"}
        if len(pnl) < window * min_windows:
            return False, {"reason": "insufficient_samples", "needed": window * min_windows, "got": int(len(pnl))}
        usable = pnl[-(window * (len(pnl) // window)):]
        wins = 0
        for i in range(0, len(usable), window):
            avg = float(np.mean(usable[i:i + window]))
            if avg < baseline_exp:
                wins += 1
        ok = wins >= min_windows
        return ok, {"windows_below": wins, "min_windows": min_windows, "baseline_expectancy": baseline_exp}

    def _shadow_eval_df(self, train_df: pd.DataFrame):
        if train_df is None or train_df.empty or "timestamp" not in train_df.columns:
            return None
        days = int(getattr(cfg, "ML_SHADOW_EVAL_DAYS", 5))
        if days <= 0:
            return None
        try:
            ts = pd.to_datetime(train_df["timestamp"], errors="coerce")
            max_ts = ts.max()
            if pd.isna(max_ts):
                return None
            cutoff = max_ts - pd.Timedelta(days=days)
            mask = ts >= cutoff
            return train_df.loc[mask].copy()
        except Exception:
            return None

    def _write_model_metadata(self, model_path: str, governance: dict, extra: dict | None = None):
        meta = {
            "model_path": str(model_path),
            "written_at": datetime.now().isoformat(),
            "governance": governance or {},
        }
        if extra:
            meta.update(extra)
        out_path = Path(model_path).with_suffix(Path(model_path).suffix + ".meta.json")
        out_path.write_text(json.dumps(meta, indent=2))

    def _should_promote(self, champ_metrics, chall_metrics, stat=None, champ_shadow=None, chall_shadow=None):
        min_diff = float(getattr(cfg, "ML_CHALLENGER_MIN_DIFF", 0.01))
        p_thr = float(getattr(cfg, "ML_PROMOTE_PVALUE", 0.1))
        champ_acc = champ_metrics.get("acc")
        chall_acc = chall_metrics.get("acc")
        champ_brier = champ_metrics.get("brier")
        chall_brier = chall_metrics.get("brier")

        # Require shadow eval
        if not champ_shadow or not chall_shadow:
            return False, "no_shadow_eval"
        if champ_shadow.get("brier") is None or chall_shadow.get("brier") is None:
            return False, "shadow_brier_missing"
        if champ_shadow.get("tail_loss") is None or chall_shadow.get("tail_loss") is None:
            return False, "shadow_tail_missing"

        # Must improve Brier on shadow AND not worsen tail loss
        if chall_shadow["brier"] >= champ_shadow["brier"]:
            return False, "shadow_brier_not_improved"
        if chall_shadow["tail_loss"] < champ_shadow["tail_loss"]:
            return False, "shadow_tail_worse"

        # Require holdout Brier improvement if available
        if champ_brier is not None and chall_brier is not None and chall_brier >= champ_brier:
            return False, "holdout_brier_not_improved"

        if champ_acc is None and chall_acc is not None:
            return True, "no_champion_acc"
        if chall_acc is None:
            return False, "no_challenger_acc"

        acc_improve = (chall_acc - (champ_acc or 0)) if chall_acc is not None else 0
        brier_improve = ((champ_brier or 0) - (chall_brier or 0)) if (champ_brier is not None and chall_brier is not None) else 0

        if stat and stat.get("p_value") is not None and stat.get("p_value") > p_thr:
            return False, f"not_significant_p{stat.get('p_value'):.3f}"
        if acc_improve >= min_diff:
            return True, f"acc_improve_{acc_improve:.3f}"
        if brier_improve >= min_diff:
            return True, f"brier_improve_{brier_improve:.3f}"
        if stat and stat.get("effect") is not None and stat.get("effect") > 0:
            return True, f"stat_effect_{stat.get('effect'):.3f}"
        return False, "not_superior"

    def _log_decision(self, decision, payload):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "decision": decision,
            "payload": payload,
        }
        try:
            self.decision_path.parent.mkdir(exist_ok=True)
            with open(self.decision_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _predict_on_df(self, predictor: TradePredictor, df: pd.DataFrame, target_col="target", segment_cols=None):
        if df is None or df.empty:
            return np.array([]), np.array([])
        segment_cols = segment_cols or []
        drop_cols = [target_col, "predicted", "pl", "sample_weight"] + segment_cols
        y = df[target_col].astype(int).values
        preds = []
        for _, row in df.iterrows():
            feats = row.drop(labels=drop_cols, errors="ignore")
            feats = pd.DataFrame([feats])
            ctx = {}
            for col in self.segment_cols:
                if col in row:
                    ctx[col] = row.get(col)
            pred = predictor.predict_confidence(feats, context=ctx)
            preds.append(pred)
        return y, np.array(preds, dtype=float)

    def _maybe_rollback(self, drift):
        if not getattr(cfg, "ML_ROLLBACK_ENABLE", False):
            return
        psi_thr = float(getattr(cfg, "ML_ROLLBACK_PSI", 0.4))
        ks_thr = float(getattr(cfg, "ML_ROLLBACK_KS", 0.4))
        sharpe_drop = float(getattr(cfg, "ML_ROLLBACK_SHARPE_DROP", 0.6))
        psi = drift.get("psi_max")
        ks = drift.get("ks_max")
        sharpe_live = drift.get("sharpe_live")
        sharpe_base = drift.get("sharpe_baseline")
        severe = False
        if psi is not None and psi > psi_thr:
            severe = True
        if ks is not None and ks > ks_thr:
            severe = True
        if sharpe_live is not None and sharpe_base is not None and (sharpe_base - sharpe_live) > sharpe_drop:
            severe = True
        if not severe:
            return
        prev = model_registry.rollback_model("xgb")
        if prev:
            try:
                self.predictor.load(prev)
                self.predictor.model_path = prev
                active_entry = model_registry.get_active_entry("xgb")
                if active_entry:
                    self.predictor.model_version = active_entry.get("hash")
                    self.predictor.model_governance = active_entry.get("governance") or {}
            except Exception:
                pass
            self._log_decision("rollback", {"reason": "drift", "drift": drift, "to": prev})


def _metrics_from_preds(y, preds, pnl=None):
    if y is None or len(y) == 0:
        return {"acc": None, "brier": None, "tail_loss": None}
    y = np.asarray(y, dtype=float)
    preds = np.asarray(preds, dtype=float)
    acc = float(np.mean((preds >= 0.5) == y))
    brier = float(np.mean((preds - y) ** 2))
    tail_loss = None
    if pnl is not None:
        try:
            arr = np.asarray(pnl, dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size >= 5:
                q = float(getattr(cfg, "ML_TAIL_LOSS_Q", 0.05))
                tail_loss = float(np.quantile(arr, q))
        except Exception:
            tail_loss = None
    return {"acc": acc, "brier": brier, "tail_loss": tail_loss}


def _psi(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if len(expected) < 2 or len(actual) < 2:
        return 0.0
    quantiles = np.quantile(expected, np.linspace(0, 1, bins + 1))
    quantiles[0] -= 1e-9
    quantiles[-1] += 1e-9
    e_counts, _ = np.histogram(expected, bins=quantiles)
    a_counts, _ = np.histogram(actual, bins=quantiles)
    e_perc = e_counts / max(len(expected), 1)
    a_perc = a_counts / max(len(actual), 1)
    psi = 0.0
    for e, a in zip(e_perc, a_perc):
        e = max(e, 1e-6)
        a = max(a, 1e-6)
        psi += (a - e) * np.log(a / e)
    return float(psi)


def _ks(expected, actual):
    expected = np.sort(np.asarray(expected, dtype=float))
    actual = np.sort(np.asarray(actual, dtype=float))
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
    data_all = np.sort(np.concatenate([expected, actual]))
    cdf_exp = np.searchsorted(expected, data_all, side="right") / len(expected)
    cdf_act = np.searchsorted(actual, data_all, side="right") / len(actual)
    return float(np.max(np.abs(cdf_exp - cdf_act)))


def _psi_from_dist(base_dist, live_dist):
    keys = set(base_dist.keys()) | set(live_dist.keys())
    psi = 0.0
    for k in keys:
        e = float(base_dist.get(k, 0.0))
        a = float(live_dist.get(k, 0.0))
        e = max(e, 1e-6)
        a = max(a, 1e-6)
        psi += (a - e) * np.log(a / e)
    return float(psi)


def _sharpe(pnl):
    pnl = np.asarray(pnl, dtype=float)
    if pnl.size < 2:
        return None
    mean = np.mean(pnl)
    std = np.std(pnl)
    if std == 0:
        return None
    return float(mean / std)
