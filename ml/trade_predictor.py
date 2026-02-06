import os
import time
import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from config import config as cfg
from core.model_registry import get_active_entry, get_shadow_entry

_SEGMENT_FIELDS = ["seg_regime", "seg_bucket", "seg_expiry", "seg_vol_q"]
_ALT_SEGMENT_FIELDS = ["regime", "time_bucket", "is_expiry", "vol_quartile"]


def _safe_float(val, default=None):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return default
        return float(val)
    except Exception:
        return default


class TradePredictor:
    def __init__(self, model_path=None, load_existing=True):
        active = get_active_entry("xgb")
        self.model_path = model_path or (active.get("path") if active else None) or getattr(cfg, "ML_MODEL_PATH", "models/xgb_live_model.pkl")
        self.models = {}
        self.feature_list = None
        self.meta = {}
        self.model_version = active.get("hash") if active else None
        self.model_governance = active.get("governance") if active else {}
        self.shadow_path = None
        self.shadow_models = {}
        self.shadow_feature_list = None
        self.shadow_meta = {}
        self.shadow_version = None
        self.shadow_governance = {}
        shadow = get_shadow_entry("xgb")
        if shadow and shadow.get("path"):
            self.shadow_path = shadow.get("path")
            self.shadow_version = shadow.get("hash")
            self.shadow_governance = shadow.get("governance") or {}
            if load_existing and os.path.exists(self.shadow_path):
                self._load_shadow(self.shadow_path)
        if load_existing and os.path.exists(self.model_path):
            self.load(self.model_path)
            print(f"[TradePredictor] Loaded model from {self.model_path}")
        else:
            self.models = {"GLOBAL": self._new_model()}
            self.feature_list = None
            self.meta = {}
            print("[TradePredictor] No model found. Initialized new XGBClassifier.")

    def _new_model(self):
        return XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
        )

    def load(self, path):
        loaded = joblib.load(path)
        if isinstance(loaded, dict) and "models" in loaded:
            self.models = loaded.get("models", {})
            self.feature_list = loaded.get("features")
            self.meta = loaded.get("meta", {})
        elif isinstance(loaded, dict) and "model" in loaded:
            self.models = {"GLOBAL": loaded.get("model")}
            self.feature_list = loaded.get("features")
            self.meta = loaded.get("meta", {})
        else:
            self.models = {"GLOBAL": loaded}
            self.feature_list = None
            self.meta = {}

    def _load_shadow(self, path):
        loaded = joblib.load(path)
        if isinstance(loaded, dict) and "models" in loaded:
            self.shadow_models = loaded.get("models", {})
            self.shadow_feature_list = loaded.get("features")
            self.shadow_meta = loaded.get("meta", {})
        elif isinstance(loaded, dict) and "model" in loaded:
            self.shadow_models = {"GLOBAL": loaded.get("model")}
            self.shadow_feature_list = loaded.get("features")
            self.shadow_meta = loaded.get("meta", {})
        else:
            self.shadow_models = {"GLOBAL": loaded}
            self.shadow_feature_list = None
            self.shadow_meta = {}

    def save(self, path=None):
        out_path = path or self.model_path
        payload = {
            "models": self.models,
            "features": self.feature_list,
            "meta": self.meta,
        }
        joblib.dump(payload, out_path)
        return out_path

    def _segment_key(self, context=None):
        if not context:
            return None
        reg_val = context.get("regime")
        if reg_val is None:
            reg_val = context.get("seg_regime")
        reg = str(reg_val or "GLOBAL").upper()
        bucket_val = context.get("time_bucket")
        if bucket_val is None:
            bucket_val = context.get("seg_bucket")
        bucket = str(bucket_val or "MID").upper()
        exp = context.get("is_expiry")
        if exp is None:
            exp = context.get("seg_expiry")
        exp_tag = "EXP" if bool(exp) else "NEXP"
        vq = context.get("vol_quartile")
        if vq is None:
            vq = context.get("seg_vol_q")
        vq = int(vq) if _safe_float(vq) is not None else 2
        return f"{reg}|{bucket}|{exp_tag}|VQ{vq}"

    def _extract_context(self, features: pd.DataFrame):
        if features is None or features.empty:
            return None
        row = features.iloc[0]
        ctx = {}
        for f in _SEGMENT_FIELDS:
            if f in row:
                ctx[f] = row.get(f)
        for f in _ALT_SEGMENT_FIELDS:
            if f in row and f not in ctx:
                ctx[f] = row.get(f)
        if not ctx:
            return None
        return ctx

    def _select_model(self, features: pd.DataFrame, context=None):
        ctx = context or self._extract_context(features)
        key = self._segment_key(ctx)
        if key and key in self.models:
            return self.models[key], key
        if "GLOBAL" in self.models:
            return self.models["GLOBAL"], "GLOBAL"
        if self.models:
            k = next(iter(self.models.keys()))
            return self.models[k], k
        # Fallback
        m = self._new_model()
        self.models = {"GLOBAL": m}
        return m, "GLOBAL"

    def align_features(self, features: pd.DataFrame, model=None) -> pd.DataFrame:
        features = features.copy()
        expected = self.feature_list
        try:
            if expected is None and model is not None:
                expected = getattr(model, "feature_names_in_", None)
            if expected is None and model is not None and hasattr(model, "get_booster"):
                expected = model.get_booster().feature_names
        except Exception:
            expected = self.feature_list

        if expected:
            for col in expected:
                if col not in features.columns:
                    features[col] = 0.0
            features = features.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            return features[list(expected)]
        # Drop segment fields if model has no explicit feature list
        drop_cols = [c for c in features.columns if c in _SEGMENT_FIELDS or c in _ALT_SEGMENT_FIELDS]
        if drop_cols:
            features = features.drop(columns=drop_cols, errors="ignore")
        return features.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def align_features_shadow(self, features: pd.DataFrame, model=None) -> pd.DataFrame:
        features = features.copy()
        expected = self.shadow_feature_list
        try:
            if expected is None and model is not None:
                expected = getattr(model, "feature_names_in_", None)
            if expected is None and model is not None and hasattr(model, "get_booster"):
                expected = model.get_booster().feature_names
        except Exception:
            expected = self.shadow_feature_list

        if expected:
            for col in expected:
                if col not in features.columns:
                    features[col] = 0.0
            features = features.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            return features[list(expected)]
        drop_cols = [c for c in features.columns if c in _SEGMENT_FIELDS or c in _ALT_SEGMENT_FIELDS]
        if drop_cols:
            features = features.drop(columns=drop_cols, errors="ignore")
        return features.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _is_fitted(self, model) -> bool:
        return hasattr(model, "classes_")

    def predict(self, features: pd.DataFrame, context=None):
        model, _ = self._select_model(features, context=context)
        feats = self.align_features(features, model=model)
        return model.predict(feats)

    def predict_proba(self, features: pd.DataFrame, context=None):
        model, _ = self._select_model(features, context=context)
        feats = self.align_features(features, model=model)
        return model.predict_proba(feats)

    def predict_confidence(self, features: pd.DataFrame, context=None) -> float:
        try:
            model, _ = self._select_model(features, context=context)
            if not self._is_fitted(model):
                return 0.5
            feats = self.align_features(features, model=model)
            proba = model.predict_proba(feats)
            if proba is None or len(proba) == 0:
                return 0.5
            if proba.shape[1] > 1:
                return float(proba[0][1])
            return float(proba[0][0])
        except Exception:
            return 0.5

    def _select_shadow_model(self, features: pd.DataFrame, context=None):
        if not self.shadow_models:
            return None, None
        ctx = context or self._extract_context(features)
        key = self._segment_key(ctx)
        if key and key in self.shadow_models:
            return self.shadow_models[key], key
        if "GLOBAL" in self.shadow_models:
            return self.shadow_models["GLOBAL"], "GLOBAL"
        k = next(iter(self.shadow_models.keys()))
        return self.shadow_models[k], k

    def predict_confidence_shadow(self, features: pd.DataFrame, context=None) -> float | None:
        try:
            model, _ = self._select_shadow_model(features, context=context)
            if model is None or not self._is_fitted(model):
                return None
            feats = self.align_features_shadow(features, model=model)
            proba = model.predict_proba(feats)
            if proba is None or len(proba) == 0:
                return None
            if proba.shape[1] > 1:
                return float(proba[0][1])
            return float(proba[0][0])
        except Exception:
            return None

    def get_governance(self):
        return {
            "model_version": self.model_version,
            "model_governance": self.model_governance,
            "shadow_version": self.shadow_version,
            "shadow_governance": self.shadow_governance,
        }

    def train_new_model(self, trade_history_df: pd.DataFrame, target_col="actual"):
        self.train_segmented(trade_history_df, target_col=target_col, segment_cols=None)

    def train_segmented(self, df: pd.DataFrame, target_col="target", segment_cols=None, min_samples=None):
        if df is None or df.empty:
            print("[TradePredictor] No data to train on.")
            return None
        segment_cols = segment_cols or []
        min_samples = min_samples or getattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 200)

        # Prepare features
        drop_cols = [target_col, "predicted", "pl", "sample_weight"]
        drop_cols += segment_cols
        X = df.drop(columns=drop_cols, errors="ignore")
        y = df[target_col]

        if X.empty or y.empty:
            print("[TradePredictor] No data to train on.")
            return None

        self.feature_list = list(X.columns)

        # Train global model
        global_model = self._new_model()
        global_model.fit(X, y)
        models = {"GLOBAL": global_model}
        meta = {
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "segments": {},
            "features": self.feature_list,
        }

        # Train segment models (keyed to match _segment_key format)
        if segment_cols:
            df = df.copy()
            def _row_key(row):
                ctx = {
                    "seg_regime": row.get("seg_regime"),
                    "seg_bucket": row.get("seg_bucket"),
                    "seg_expiry": row.get("seg_expiry"),
                    "seg_vol_q": row.get("seg_vol_q"),
                }
                return self._segment_key(ctx)
            df["__seg_key"] = df.apply(_row_key, axis=1)
            for seg_key, grp in df.groupby("__seg_key"):
                try:
                    n = len(grp)
                    if n < min_samples or not seg_key:
                        continue
                    Xs = grp.drop(columns=drop_cols + ["__seg_key"], errors="ignore")
                    ys = grp[target_col]
                    model = self._new_model()
                    model.fit(Xs, ys)
                    models[seg_key] = model
                    meta["segments"][seg_key] = {"n": n}
                except Exception:
                    continue

        self.models = models
        self.meta = meta
        return meta

    def evaluate(self, df: pd.DataFrame, target_col="target", segment_cols=None):
        if df is None or df.empty:
            return {"acc": None, "brier": None}
        segment_cols = segment_cols or []
        drop_cols = [target_col, "predicted", "pl", "sample_weight"] + segment_cols
        y = df[target_col].astype(int).values
        preds = []
        for _, row in df.iterrows():
            feats = row.drop(labels=drop_cols, errors="ignore")
            feats = pd.DataFrame([feats])
            ctx = {}
            for col in _SEGMENT_FIELDS:
                if col in row:
                    ctx[col] = row.get(col)
            for col in _ALT_SEGMENT_FIELDS:
                if col in row and col not in ctx:
                    ctx[col] = row.get(col)
            pred = self.predict_confidence(feats, context=ctx)
            preds.append(pred)
        preds = np.array(preds, dtype=float)
        acc = float(np.mean((preds >= 0.5) == y)) if len(y) else None
        brier = float(np.mean((preds - y) ** 2)) if len(y) else None
        return {"acc": acc, "brier": brier}

    def update_model_online(self, new_trades_df: pd.DataFrame, target_col="actual"):
        print("[TradePredictor] Online model update started...")
        self.train_new_model(new_trades_df, target_col=target_col)
        print("[TradePredictor] Online model update complete.")
