import os
import time
import tempfile
import threading
import logging
import joblib
import numpy as np
import pandas as pd
try:
    from xgboost import XGBClassifier as _XGBClassifier
    _XGB_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - runtime dependency failure path
    _XGBClassifier = None
    _XGB_IMPORT_ERROR = f"{type(exc).__name__}:{exc}"
from sklearn.dummy import DummyClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from config import config as cfg
from core.feature_contract import FeatureContract
from core.model_registry import get_active_entry, get_shadow_entry

_SEGMENT_FIELDS = ["seg_regime", "seg_bucket", "seg_expiry", "seg_vol_q"]
_ALT_SEGMENT_FIELDS = ["regime", "time_bucket", "is_expiry", "vol_quartile"]
logger = logging.getLogger(__name__)


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
        self.xgb_available = _XGBClassifier is not None
        self.model_runtime = "xgboost" if self.xgb_available else "dummy"
        self._xgb_warned = False
        shadow = get_shadow_entry("xgb")
        if shadow and shadow.get("path"):
            self.shadow_path = shadow.get("path")
            self.shadow_version = shadow.get("hash")
            self.shadow_governance = shadow.get("governance") or {}
            if load_existing and os.path.exists(self.shadow_path):
                try:
                    self._load_shadow(self.shadow_path)
                except Exception as exc:
                    print(f"[TradePredictor][WARN] shadow_load_failed path={self.shadow_path} err={type(exc).__name__}:{exc}")
                    self.shadow_models = {}
                    self.shadow_feature_list = None
                    self.shadow_meta = {}
        if load_existing and os.path.exists(self.model_path):
            try:
                self.load(self.model_path)
                print(f"[TradePredictor] Loaded model from {self.model_path}")
            except Exception as exc:
                self.models = {"GLOBAL": self._new_model()}
                self.feature_list = None
                self.meta = {"degraded_reason": f"model_load_failed:{type(exc).__name__}:{exc}"}
                print(
                    f"[TradePredictor][DEGRADED] model_load_failed path={self.model_path} "
                    f"err={type(exc).__name__}:{exc}"
                )
        else:
            self.models = {"GLOBAL": self._new_model()}
            self.feature_list = None
            self.meta = {}
            if self.xgb_available:
                print("[TradePredictor] No model found. Initialized new XGBClassifier.")
            else:
                print(
                    "[TradePredictor][DEGRADED] No model found and xgboost runtime unavailable. "
                    "Initialized DummyClassifier."
                )
        self._model_lock = threading.RLock()
        self._online_update_lock = threading.Lock()
        self._online_update_thread = None
        self._online_update_state = {
            "running": False,
            "duration_ms": None,
            "success": None,
            "failure": None,
            "last_started_epoch_ms": None,
            "last_completed_epoch_ms": None,
        }
        self.feature_contract = self._build_feature_contract()

    def _ensure_runtime_state(self):
        if not hasattr(self, "_model_lock"):
            self._model_lock = threading.RLock()
        if not hasattr(self, "_online_update_lock"):
            self._online_update_lock = threading.Lock()
        if not hasattr(self, "_online_update_thread"):
            self._online_update_thread = None
        if not hasattr(self, "_online_update_state"):
            self._online_update_state = {
                "running": False,
                "duration_ms": None,
                "success": None,
                "failure": None,
                "last_started_epoch_ms": None,
                "last_completed_epoch_ms": None,
            }

    def _new_model(self):
        if _XGBClassifier is not None:
            return _XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric="logloss",
            )
        if not self._xgb_warned:
            self._xgb_warned = True
            print(
                "[TradePredictor][DEGRADED] xgboost runtime unavailable; "
                f"fallback=DummyClassifier reason={_XGB_IMPORT_ERROR}"
            )
        return DummyClassifier(strategy="prior")

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
        self.feature_contract = self._build_feature_contract()

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

    def _build_feature_contract(self) -> FeatureContract:
        fallback = []
        try:
            fallback = list(getattr(cfg, "MODEL_REQUIRED_FEATURES", []) or [])
        except Exception:
            fallback = []
        return FeatureContract.from_model_metadata(
            model_features=list(self.feature_list or []),
            fallback_features=fallback,
        )

    def get_feature_contract(self) -> FeatureContract:
        if not isinstance(getattr(self, "feature_contract", None), FeatureContract):
            self.feature_contract = self._build_feature_contract()
        return self.feature_contract

    def save(self, path=None):
        out_path = path or self.model_path
        self._ensure_runtime_state()
        with self._model_lock:
            payload = {
                "models": self.models,
                "features": self.feature_list,
                "meta": self.meta,
            }
        out_file = str(out_path)
        out_dir = os.path.dirname(out_file) or "."
        os.makedirs(out_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".model_tmp_", suffix=".pkl", dir=out_dir)
        os.close(fd)
        try:
            joblib.dump(payload, tmp_path)
            os.replace(tmp_path, out_file)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
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
        self._ensure_runtime_state()
        with self._model_lock:
            models = dict(self.models or {})
        ctx = context or self._extract_context(features)
        key = self._segment_key(ctx)
        if key and key in models:
            return models[key], key
        if "GLOBAL" in models:
            return models["GLOBAL"], "GLOBAL"
        if models:
            k = next(iter(models.keys()))
            return models[k], k
        # Fallback
        m = self._new_model()
        with self._model_lock:
            self.models = {"GLOBAL": m}
        return m, "GLOBAL"

    def align_features(self, features: pd.DataFrame, model=None) -> pd.DataFrame:
        features = features.copy()
        self._ensure_runtime_state()
        with self._model_lock:
            expected = list(self.feature_list) if self.feature_list is not None else None
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
        self._ensure_runtime_state()
        with self._model_lock:
            expected = list(self.shadow_feature_list) if self.shadow_feature_list is not None else None
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

    def predict_calibrated_proba(self, features: pd.DataFrame, context=None) -> float:
        """
        Canonical calibrated probability used by sizing and gating.
        Falls back to raw model proba with optional temperature smoothing.
        """
        raw = self.predict_confidence(features, context=context)
        try:
            p = float(raw)
        except Exception:
            p = 0.5
        p = max(1e-6, min(1.0 - 1e-6, p))
        try:
            temperature = float(getattr(cfg, "ML_PROBA_TEMPERATURE", 1.0) or 1.0)
        except Exception:
            temperature = 1.0
        if temperature <= 0:
            temperature = 1.0
        if abs(temperature - 1.0) < 1e-9:
            return float(max(0.0, min(1.0, p)))
        logit = np.log(p / (1.0 - p))
        calibrated = 1.0 / (1.0 + np.exp(-(logit / temperature)))
        return float(max(0.0, min(1.0, calibrated)))

    def _select_shadow_model(self, features: pd.DataFrame, context=None):
        self._ensure_runtime_state()
        with self._model_lock:
            shadow_models = dict(self.shadow_models or {})
        if not shadow_models:
            return None, None
        ctx = context or self._extract_context(features)
        key = self._segment_key(ctx)
        if key and key in shadow_models:
            return shadow_models[key], key
        if "GLOBAL" in shadow_models:
            return shadow_models["GLOBAL"], "GLOBAL"
        k = next(iter(shadow_models.keys()))
        return shadow_models[k], k

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

    def _train_segmented_payload(self, df: pd.DataFrame, target_col="target", segment_cols=None, min_samples=None):
        if df is None or df.empty:
            return None
        segment_cols = segment_cols or []
        min_samples = min_samples or getattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 200)

        drop_cols = [target_col, "predicted", "pl", "sample_weight"]
        drop_cols += segment_cols
        X = df.drop(columns=drop_cols, errors="ignore")
        y = df[target_col]

        if X.empty or y.empty:
            return None

        feature_list = list(X.columns)
        global_model = self._new_model()
        global_model.fit(X, y)
        models = {"GLOBAL": global_model}
        meta = {
            "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "segments": {},
            "features": feature_list,
        }

        if segment_cols:
            df_seg = df.copy()

            def _row_key(row):
                ctx = {
                    "seg_regime": row.get("seg_regime"),
                    "seg_bucket": row.get("seg_bucket"),
                    "seg_expiry": row.get("seg_expiry"),
                    "seg_vol_q": row.get("seg_vol_q"),
                }
                return self._segment_key(ctx)

            df_seg["__seg_key"] = df_seg.apply(_row_key, axis=1)
            for seg_key, grp in df_seg.groupby("__seg_key"):
                try:
                    n = len(grp)
                    if n < min_samples or not seg_key:
                        continue
                    Xs = grp.drop(columns=drop_cols + ["__seg_key"], errors="ignore")
                    ys = grp[target_col]
                    if Xs.empty or ys.empty:
                        continue
                    model = self._new_model()
                    model.fit(Xs, ys)
                    models[seg_key] = model
                    meta["segments"][seg_key] = {"n": n}
                except Exception:
                    continue
        return {"models": models, "features": feature_list, "meta": meta}

    def _validate_payload_predict(self, payload: dict, df: pd.DataFrame, target_col: str):
        models = payload.get("models") or {}
        if not models:
            raise ValueError("trained_models_empty")
        model = models.get("GLOBAL") or next(iter(models.values()))
        drop_cols = [target_col, "predicted", "pl", "sample_weight"]
        X = df.drop(columns=drop_cols, errors="ignore")
        if X.empty:
            raise ValueError("validation_features_empty")
        feat = X.head(1).copy()
        expected = payload.get("features") or []
        if expected:
            for col in expected:
                if col not in feat.columns:
                    feat[col] = 0.0
            feat = feat[list(expected)]
        feat = feat.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        _ = model.predict(feat)

    def train_segmented(self, df: pd.DataFrame, target_col="target", segment_cols=None, min_samples=None):
        payload = self._train_segmented_payload(
            df, target_col=target_col, segment_cols=segment_cols, min_samples=min_samples
        )
        if payload is None:
            print("[TradePredictor] No data to train on.")
            return None
        self._ensure_runtime_state()
        with self._model_lock:
            self.models = payload.get("models") or {"GLOBAL": self._new_model()}
            self.feature_list = payload.get("features")
            self.meta = payload.get("meta") or {}
            self.feature_contract = self._build_feature_contract()
            return self.meta

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
        self._ensure_runtime_state()
        if new_trades_df is None or new_trades_df.empty:
            logger.info("online_model_update skipped: empty_dataset")
            return {"started": False, "completed": True, "success": False, "reason": "empty_dataset"}

        async_enabled = bool(getattr(cfg, "ML_ONLINE_UPDATE_ASYNC", True))
        max_block_sec = float(getattr(cfg, "ML_ONLINE_UPDATE_MAX_BLOCK_SEC", 0.2) or 0.2)

        def _worker():
            start = time.perf_counter()
            failure = None
            success = False
            try:
                payload = self._train_segmented_payload(
                    new_trades_df,
                    target_col=target_col,
                    segment_cols=None,
                    min_samples=getattr(cfg, "ML_SEGMENT_MIN_SAMPLES", 200),
                )
                if payload is None:
                    raise ValueError("no_training_payload")
                self._validate_payload_predict(payload, new_trades_df, target_col=target_col)
                with self._model_lock:
                    self.models = payload.get("models") or {"GLOBAL": self._new_model()}
                    self.feature_list = payload.get("features")
                    self.meta = payload.get("meta") or {}
                    self.feature_contract = self._build_feature_contract()
                try:
                    self.save(self.model_path)
                except Exception as exc:
                    logger.warning("online_model_update save_failed err=%s", f"{type(exc).__name__}:{exc}")
                success = True
            except Exception as exc:
                failure = f"{type(exc).__name__}:{exc}"
                logger.exception("online_model_update failed")
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000.0)
                with self._online_update_lock:
                    self._online_update_state.update(
                        {
                            "running": False,
                            "duration_ms": duration_ms,
                            "success": success,
                            "failure": failure,
                            "last_completed_epoch_ms": int(time.time() * 1000.0),
                        }
                    )
                logger.info(
                    "online_model_update completed duration_ms=%s success=%s failure=%s",
                    duration_ms,
                    success,
                    failure or "",
                )

        with self._online_update_lock:
            thread = self._online_update_thread
            if thread is not None and thread.is_alive():
                logger.info("online_model_update skipped: already_running")
                return {"started": False, "completed": False, "success": None, "reason": "already_running"}
            self._online_update_state.update(
                {
                    "running": True,
                    "duration_ms": None,
                    "success": None,
                    "failure": None,
                    "last_started_epoch_ms": int(time.time() * 1000.0),
                }
            )
            thread = threading.Thread(
                target=_worker,
                name="trade-predictor-online-update",
                daemon=True,
            )
            self._online_update_thread = thread

        logger.info("online_model_update started async=%s max_block_sec=%.3f", async_enabled, max_block_sec)
        print("[TradePredictor] Online model update started...")

        if async_enabled:
            thread.start()
            if max_block_sec > 0:
                thread.join(timeout=max_block_sec)
            completed = not thread.is_alive()
            if completed:
                with self._online_update_lock:
                    state = dict(self._online_update_state)
                return {
                    "started": True,
                    "completed": True,
                    "success": bool(state.get("success")),
                    "duration_ms": state.get("duration_ms"),
                    "failure": state.get("failure"),
                }
            return {"started": True, "completed": False, "success": None}

        # Synchronous bounded path (explicitly configured)
        thread.start()
        thread.join()
        with self._online_update_lock:
            state = dict(self._online_update_state)
        return {
            "started": True,
            "completed": True,
            "success": bool(state.get("success")),
            "duration_ms": state.get("duration_ms"),
            "failure": state.get("failure"),
        }

    def wait_for_online_update(self, timeout_sec: float = 5.0) -> bool:
        self._ensure_runtime_state()
        thread = self._online_update_thread
        if thread is None:
            return True
        thread.join(timeout=max(0.0, float(timeout_sec)))
        return not thread.is_alive()
