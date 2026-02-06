import joblib
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os
from config import config as cfg

class TradePredictor:
    def __init__(self, model_path=None):
        """
        Initialize predictor
        """
        self.model_path = model_path or getattr(cfg, "ML_MODEL_PATH", "models/xgb_options_model.pkl")

        # Load existing model if available, else create a new one
        if os.path.exists(self.model_path):
            loaded = joblib.load(self.model_path)
            if isinstance(loaded, dict) and "model" in loaded:
                self.xgb_model = loaded["model"]
                self.feature_list = loaded.get("features")
            else:
                self.xgb_model = loaded
                self.feature_list = None
            print(f"[TradePredictor] Loaded model from {self.model_path}")
        else:
            self.xgb_model = XGBClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.1
            )
            self.feature_list = None
            print("[TradePredictor] No model found. Initialized new XGBClassifier.")

    def predict(self, features: pd.DataFrame):
        """
        Predict trade signal for given features
        Returns array of predictions
        """
        return self.xgb_model.predict(features)

    def predict_proba(self, features: pd.DataFrame):
        """
        Predict probability for each class
        Useful for confidence scoring
        """
        return self.xgb_model.predict_proba(features)

    def align_features(self, features: pd.DataFrame) -> pd.DataFrame:
        """
        Align incoming features to the model's expected columns.
        Missing columns are filled with 0; extra columns are dropped.
        """
        try:
            expected = self.feature_list or getattr(self.xgb_model, "feature_names_in_", None)
            if expected is None and hasattr(self.xgb_model, "get_booster"):
                expected = self.xgb_model.get_booster().feature_names
            if not expected:
                return features
            for col in expected:
                if col not in features.columns:
                    features[col] = 0
            return features[list(expected)]
        except Exception:
            return features

    def _is_fitted(self) -> bool:
        return hasattr(self.xgb_model, "classes_")

    def predict_confidence(self, features: pd.DataFrame) -> float:
        """
        Returns probability of the positive class if available.
        """
        try:
            if not self._is_fitted():
                return 0.5
            features = self.align_features(features)
            proba = self.predict_proba(features)
            if proba is None or len(proba) == 0:
                return 0.5
            # Assume positive class is index 1
            return float(proba[0][1]) if proba.shape[1] > 1 else float(proba[0][0])
        except Exception:
            return 0.5

    def train_new_model(self, trade_history_df: pd.DataFrame, target_col="actual"):
        """
        Retrain model on new trade history
        trade_history_df: DataFrame containing features + 'actual' column
        target_col: name of target column
        """
        # Drop non-feature columns
        sample_weight = None
        if "sample_weight" in trade_history_df.columns:
            sample_weight = trade_history_df["sample_weight"].values
        X = trade_history_df.drop(columns=[target_col, "predicted", "pl", "sample_weight"], errors='ignore')
        y = trade_history_df[target_col]

        if X.empty or y.empty:
            print("[TradePredictor] No data to train on.")
            return

        # Split for training/testing (optional, can skip if retraining on all)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=42)
        if sample_weight is not None:
            sw_train, sw_test = train_test_split(sample_weight, test_size=0.1, random_state=42)
        else:
            sw_train = sw_test = None

        # Train
        if sw_train is not None:
            self.xgb_model.fit(X_train, y_train, sample_weight=sw_train)
        else:
            self.xgb_model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.xgb_model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        print(f"[TradePredictor] Model retrained. Test Accuracy: {acc:.2f}")

        # Save updated model
        joblib.dump(self.xgb_model, self.model_path)
        print(f"[TradePredictor] Model saved to {self.model_path}")

    def update_model_online(self, new_trades_df: pd.DataFrame, target_col="actual"):
        """
        Online update if incremental training is needed.
        Can be called every N trades.
        """
        print("[TradePredictor] Online model update started...")
        self.train_new_model(new_trades_df, target_col=target_col)
        print("[TradePredictor] Online model update complete.")
