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
from core.events import append_event as append_runtime_event
from core.feature_contract import FeatureContract
from core.model_registry import get_active_entry, get_shadow_entry
from core.runtime_lifecycle import lifecycle

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


def _record_startup_boundary(event: str, *, details=None, error: str | None = None) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        payload = {"is_order_action": False}
        if details:
            payload.update(dict(details))
        record_runtime_startup_event(
            event,
            source="ml.trade_predictor.TradePredictor.__init__",
            details=payload,
            error=error,
        )
    except Exception:
        pass


class TradePredictor:
    def __init__(self, model_path=None, load_existing=True):
        _record_startup_boundary(
            "ORCHESTRATOR_PREDICTOR_INIT_STARTED",
            details={"load_existing": bool(load_existing)},
        )
        try:
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
            self.execution_mode = str(
                getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))
            ).upper()
            shadow = get_shadow_entry("xgb")
            if shadow and shadow.get("path"):
                self.shadow_path = shadow.get("path")
                self.shadow_version = shadow.get("hash")
                self.shadow_governance = shadow.get("governance") or {}
            non_live_skip_persisted_load = bool(
                load_existing
                and self.execution_mode != "LIVE"
                and bool(getattr(cfg, "NONLIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", True))
            )
            live_skip_persisted_load = bool(
                load_existing
                and self.execution_mode == "LIVE"
                and bool(getattr(cfg, "LIVE_PREDICTOR_SKIP_PERSISTED_MODEL_LOAD", False))
            )
            startup_skip_reason = None
            if live_skip_persisted_load:
                startup_skip_reason = "live_startup_skip_persisted_model_load"
            elif non_live_skip_persisted_load:
                startup_skip_reason = "nonlive_startup_skip_persisted_model_load"

            if startup_skip_reason:
                self.xgb_available = False
                self.model_runtime = "dummy"
                self.models = {"GLOBAL": DummyClassifier(strategy="prior")}
                self.feature_list = None
                self.meta = {
                    "degraded_reason": startup_skip_reason,
                    "execution_mode": self.execution_mode,
                    "model_path": self.model_path,
                }
                self._emit_predictor_degraded_startup(
                    reason=startup_skip_reason,
                    load_existing=load_existing,
                )
            else:
                if self.shadow_path and load_existing and os.path.exists(self.shadow_path):
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
            self._online_update_stop_event = threading.Event()
            self._online_update_state = {
                "running": False,
                "duration_ms": None,
                "success": None,
                "failure": None,
                "last_started_epoch_ms": None,
                "last_completed_epoch_ms": None,
            }
            self.feature_contract = self._build_feature_contract()
        except Exception as exc:
            _record_startup_boundary(
                "ORCHESTRATOR_PREDICTOR_INIT_FAILED",
                error=f"{type(exc).__name__}:{exc}",
            )
            raise
        _record_startup_boundary(
            "ORCHESTRATOR_PREDICTOR_INIT_COMPLETED",
            details={
                "execution_mode": getattr(self, "execution_mode", ""),
                "model_runtime": getattr(self, "model_runtime", ""),
                "xgb_available": bool(getattr(self, "xgb_available", False)),
            },
        )

    def _emit_predictor_degraded_startup(self, *, reason: str, load_existing: bool) -> None:
        payload = {
            "event": "predictor_degraded_startup",
            "reason": str(reason),
            "execution_mode": str(self.execution_mode or ""),
            "model_path": str(self.model_path or ""),
            "model_runtime": str(self.model_runtime or ""),
            "load_existing": bool(load_existing),
            "live_mode": bool(str(self.execution_mode or "").upper() == "LIVE"),
        }
        logger.warning(
            "predictor_degraded_startup execution_mode=%s reason=%s model_path=%s model_runtime=%s load_existing=%s",
            payload["execution_mode"],
            payload["reason"],
            payload["model_path"],
            payload["model_runtime"],
            payload["load_existing"],
        )
        try:
            append_runtime_event("predictor_degraded_startup", payload)
        except Exception:
            pass
        print(
            "[TradePredictor][DEGRADED_STARTUP] "
            f"mode={payload['execution_mode']} reason={payload['reason']} "
            f"model_path={payload['model_path']} runtime={payload['model_runtime']}"
        )

    def _ensure_runtime_state(self):
        if not hasattr(self, "_model_lock"):
            self._model_lock = threading.RLock()
        if not hasattr(self, "_online_update_lock"):
            self._online_update_lock = threading.Lock()
        if not hasattr(self, "_online_update_thread"):
            self._online_update_thread = None
        if not hasattr(self, "_online_update_stop_event"):
            self._online_update_stop_event = threading.Event()
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
            joblib.dump(payload, out_path)

    def train(self, X, y):
        if "segment" in X.columns and any(col not in X.columns for col in _SEGMENT_FIELDS):
            parts = X["segment"].astype(str).str.split("|", expand=True)
            for idx, col in enumerate(_SEGMENT_FIELDS):
                X[col] = parts[idx] if idx < parts.shape[1] else "unknown"
        for col in _SEGMENT_FIELDS:
            if col not in X.columns:
                X[col] = "unknown"
        for col in _ALT_SEGMENT_FIELDS:
            if col not in X.columns:
                X[col] = "unknown"
        self.feature_list = list(X.columns)
        self.models = {}
        try:
            append_runtime_event("model_training_started", {"rows": int(len(X)), "segments": int(len(X[_SEGMENT_FIELDS].drop_duplicates())) if set(_SEGMENT_FIELDS).issubset(X.columns) else 0})
        except Exception:
            pass
        # Train global model
        if _XGBClassifier is not None:
            global_model = self._new_model()
            global_model.fit(pd.get_dummies(X), y)
        else:
            global_model = DummyClassifier(strategy="most_frequent")
            global_model.fit(pd.get_dummies(X), y)
        self.models["GLOBAL"] = global_model
        # Train segment models with minimum sample threshold
        seg_keys = []
        if set(_SEGMENT_FIELDS).issubset(X.columns):
            seg_keys = _SEGMENT_FIELDS
        elif set(_ALT_SEGMENT_FIELDS).issubset(X.columns):
            seg_keys = _ALT_SEGMENT_FIELDS
        if seg_keys:
            for seg, df in X.groupby(seg_keys):
                key = "|".join(map(str, seg if isinstance(seg, tuple) else (seg,)))
                idx = df.index
                if len(df) >= 50:
                    if _XGBClassifier is not None:
                        m = self._new_model()
                        m.fit(pd.get_dummies(df), y.loc[idx])
                    else:
                        m = DummyClassifier(strategy="most_frequent")
                        m.fit(pd.get_dummies(df), y.loc[idx])
                    self.models[key] = m

    def predict_confidence(self, features):
        self._ensure_runtime_state()
        if not self.models:
            return 0.5
        df = pd.DataFrame([features])
        # align columns
        if self.feature_list is not None:
            for col in self.feature_list:
                if col not in df.columns:
                    df[col] = 0
            df = df[self.feature_list]
        df = pd.get_dummies(df)
        # Choose segment-specific model
