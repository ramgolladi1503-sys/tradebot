import pandas as pd
import joblib
from ml.trade_predictor import TradePredictor
from core.model_health import ModelHealth

class AutoRetrain:
    def __init__(self, predictor: TradePredictor, model_path="models/xgb_options_model.pkl"):
        self.predictor = predictor
        self.model_path = model_path
        self.health_checker = ModelHealth()

    def update_model(self, trade_history_file="data/trade_log.csv"):
        # Load trade history
        try:
            trades_df = pd.read_csv(trade_history_file)
        except Exception:
            print("[AutoRetrain] Trade log not found or unreadable.")
            return

        required_cols = {"predicted", "actual"}
        if not required_cols.issubset(trades_df.columns):
            print("[AutoRetrain] Trade log missing 'predicted'/'actual' columns.")
            return

        # retrain guard: min trades + cooldown
        if len(trades_df) < getattr(__import__("config.config", fromlist=["RETRAIN_MIN_TRADES"]), "RETRAIN_MIN_TRADES", 50):
            print("[AutoRetrain] Not enough trades to retrain.")
            return
        import time, json
        from pathlib import Path
        cooldown = getattr(__import__("config.config", fromlist=["RETRAIN_COOLDOWN_MIN"]), "RETRAIN_COOLDOWN_MIN", 180) * 60
        state_path = Path("logs/last_retrain.json")
        last_ts = 0
        if state_path.exists():
            try:
                last_ts = json.loads(state_path.read_text()).get("ts", 0)
            except Exception:
                last_ts = 0
        if time.time() - last_ts < cooldown:
            print("[AutoRetrain] Retrain cooldown active.")
            return
        if self.health_checker.check_model_performance(trades_df):
            print("[AutoRetrain] Retraining ML model...")
            # Retrain XGB / other model
            self.predictor.train_new_model(trades_df)
            # Save updated model only if improved
            try:
                metrics_path = Path("logs/model_metrics.json")
                last_acc = 0
                if metrics_path.exists():
                    last_acc = json.loads(metrics_path.read_text()).get("acc", 0)
                recent = trades_df.tail(100)
                acc = (recent["predicted"] == recent["actual"]).mean()
                if acc >= last_acc:
                    joblib.dump(self.predictor.xgb_model, self.model_path)
                    metrics_path.parent.mkdir(exist_ok=True)
                    metrics_path.write_text(json.dumps({"acc": acc}))
                    print("[AutoRetrain] Model retrained and saved.")
                else:
                    print("[AutoRetrain] Retrain did not improve; keeping old model.")
            except Exception:
                joblib.dump(self.predictor.xgb_model, self.model_path)
            state_path.parent.mkdir(exist_ok=True)
            state_path.write_text(json.dumps({"ts": time.time()}))
        else:
            print("[AutoRetrain] Model healthy. No retraining needed.")
