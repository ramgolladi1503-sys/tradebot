from __future__ import annotations
from core.paths import data_root, logs_dir

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

# Keep training headless-safe by default for CLI and subprocess runners.
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# Allow direct invocation (`python /abs/path/models/train_micro_model.py`) without
# requiring the caller to pre-set PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from config import config as cfg
except Exception:
    cfg = SimpleNamespace(TRADE_DB_PATH=str(data_root() / "trades.db"), MICRO_MODEL_PATH="models/microstructure_model.h5")

from models.tick_dataset import build_tick_dataset


def _safe_float(value, default=0.0) -> float:
    try:
        out = float(value)
        if np.isfinite(out):
            return out
    except Exception:
        pass
    return float(default)


def _as_path(raw: str | None) -> Path | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return Path(text)


def _load_csv_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"csv_not_found:{path}")
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _derive_features(df: pd.DataFrame, horizon: int, threshold: float) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out

    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
        out = out.sort_values("timestamp")
    if "last_price" not in out.columns and "close" in out.columns:
        out["last_price"] = pd.to_numeric(out["close"], errors="coerce")
    out["last_price"] = pd.to_numeric(out.get("last_price"), errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    if "oi" not in out.columns:
        out["oi"] = 0.0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    out["oi"] = pd.to_numeric(out["oi"], errors="coerce").fillna(0.0)

    has_group = "instrument_token" in out.columns
    if has_group:
        out = out.sort_values(["instrument_token", "timestamp"] if "timestamp" in out.columns else ["instrument_token"])
        grp = out.groupby("instrument_token", sort=False)
        out["return_1"] = grp["last_price"].pct_change()
        out["volume_delta"] = grp["volume"].diff()
        out["oi_delta"] = grp["oi"].diff()
        future_px = grp["last_price"].shift(-int(horizon))
    else:
        out["return_1"] = out["last_price"].pct_change()
        out["volume_delta"] = out["volume"].diff()
        out["oi_delta"] = out["oi"].diff()
        future_px = out["last_price"].shift(-int(horizon))

    if "depth_spread_pct" in out.columns:
        out["spread_pct"] = pd.to_numeric(out["depth_spread_pct"], errors="coerce")
    elif {"high", "low", "last_price"}.issubset(set(out.columns)):
        high = pd.to_numeric(out["high"], errors="coerce")
        low = pd.to_numeric(out["low"], errors="coerce")
        px = pd.to_numeric(out["last_price"], errors="coerce")
        out["spread_pct"] = (high - low) / px.replace(0, np.nan)
    else:
        out["spread_pct"] = 0.0

    out["oi_change"] = pd.to_numeric(out["oi_delta"], errors="coerce")
    if "target" not in out.columns:
        ret = (future_px - out["last_price"]) / out["last_price"].replace(0, np.nan)
        out["target"] = (ret > float(threshold)).astype(int)
    else:
        out["target"] = pd.to_numeric(out["target"], errors="coerce")

    for col in ("return_1", "volume_delta", "oi_delta", "spread_pct", "oi_change"):
        out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)

    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=["last_price", "target"])
    out = out[out["last_price"] > 0]
    out["target"] = out["target"].astype(int)
    return out


def _build_dataset(args) -> tuple[pd.DataFrame, str]:
    source = "unknown"
    csv_path = _as_path(args.csv_path)
    if csv_path:
        try:
            df = _load_csv_dataset(csv_path)
            return _derive_features(df, args.horizon, args.threshold), f"csv:{csv_path}"
        except Exception as exc:
            return pd.DataFrame(), f"csv_error:{type(exc).__name__}:{csv_path}"

    db_path = _as_path(args.db_path)
    if db_path and db_path.exists():
        try:
            df = build_tick_dataset(
                db_path=str(db_path),
                horizon=args.horizon,
                threshold=args.threshold,
                out_path=None,
                from_depth=bool(args.from_depth),
                depth_tolerance_sec=float(args.depth_tolerance_sec),
            )
            if not df.empty:
                return _derive_features(df, args.horizon, args.threshold), f"db:{db_path}"
            source = f"db_empty:{db_path}"
        except Exception as exc:
            source = f"db_error:{type(exc).__name__}"
    else:
        source = f"db_missing:{db_path}"

    # Fallback deterministic local datasets
    candidates = [
        data_root() / "tick_features.csv",
        data_root() / "NIFTY_from_ticks_5m.csv",
    ]
    for path in candidates:
        if path.exists():
            df = _load_csv_dataset(path)
            return _derive_features(df, args.horizon, args.threshold), f"csv_fallback:{path}"

    return pd.DataFrame(), source


def _write_feature_importance(model, feature_names: list[str], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    weights = None
    if hasattr(model, "coef_"):
        try:
            coef = np.asarray(getattr(model, "coef_"), dtype=float)
            if coef.ndim == 2:
                weights = np.mean(np.abs(coef), axis=0)
            elif coef.ndim == 1:
                weights = np.abs(coef)
        except Exception:
            weights = None
    if weights is None and hasattr(model, "feature_importances_"):
        try:
            weights = np.asarray(getattr(model, "feature_importances_"), dtype=float)
        except Exception:
            weights = None
    for layer in getattr(model, "layers", []):
        try:
            params = layer.get_weights()
            if params and len(params) >= 1 and np.ndim(params[0]) == 2:
                weights = params[0]
                break
        except Exception:
            continue
    if weights is None:
        imp = np.ones(len(feature_names), dtype=float)
    elif np.ndim(weights) == 1:
        imp = np.asarray(weights, dtype=float)
    else:
        imp = np.mean(np.abs(weights), axis=1)
    n = min(len(feature_names), len(imp))
    rows = [{"feature": str(feature_names[i]), "importance": float(imp[i])} for i in range(n)]
    pd.DataFrame(rows).sort_values("importance", ascending=False).to_csv(out_path, index=False)


def _train(args) -> tuple[int, dict]:
    start = time.time()
    df, source = _build_dataset(args)
    report = {
        "source": source,
        "status": "INIT",
        "rows": int(len(df)),
        "target_positive_rate": None,
        "model_path": str(args.model_path),
        "feature_importance_path": str(args.feature_importance_path),
    }

    if df.empty:
        report["status"] = "NO_DATA"
        report["reason"] = "No training data found. Provide --csv-path or ensure ticks exist in DB."
        return 2, report

    y = pd.to_numeric(df["target"], errors="coerce").fillna(0).astype(int).values
    classes = sorted(set(int(v) for v in y.tolist()))
    report["target_positive_rate"] = float(np.mean(y)) if len(y) else 0.0
    report["class_labels"] = classes

    min_rows = max(20, int(args.min_rows))
    if len(df) < min_rows:
        report["status"] = "INSUFFICIENT_ROWS"
        report["reason"] = f"Need >= {min_rows} rows, got {len(df)}"
        return 2, report
    if len(classes) < 2:
        report["status"] = "INSUFFICIENT_CLASS_VARIANCE"
        report["reason"] = f"Need binary targets, got classes={classes}"
        return 3, report

    if bool(args.dry_run):
        report["status"] = "DRY_RUN_OK"
        report["elapsed_sec"] = round(time.time() - start, 3)
        return 0, report

    try:
        from ml.microstructure_model import prepare_microstructure_features
    except Exception as exc:
        report["status"] = "IMPORT_FAILED"
        report["reason"] = f"{type(exc).__name__}: {exc}"
        return 4, report

    x, feature_names = prepare_microstructure_features(df, return_names=True)
    mask = np.isfinite(x).all(axis=1)
    x = x[mask]
    y = y[mask]
    if len(y) < min_rows:
        report["status"] = "INSUFFICIENT_VALID_ROWS"
        report["reason"] = f"After feature filtering rows={len(y)} < min_rows={min_rows}"
        return 2, report

    split = int(round(len(y) * (1.0 - float(args.val_split))))
    split = max(1, min(split, len(y) - 1))
    x_train, x_val = x[:split], x[split:]
    y_train, y_val = y[:split], y[split:]

    backend = str(args.backend or "auto").strip().lower()
    if backend not in {"auto", "tensorflow", "sklearn"}:
        backend = "auto"
    backend_used = None
    model = None
    history = None
    val_loss = None
    val_acc = None
    tf_reason = None
    model_path = Path(args.model_path)

    if backend in {"auto", "tensorflow"}:
        try:
            from ml.microstructure_model import build_microstructure_model

            model = build_microstructure_model(input_dim=x.shape[1])
            callbacks = []
            try:
                import tensorflow as tf

                callbacks.append(
                    tf.keras.callbacks.EarlyStopping(
                        monitor="val_loss",
                        patience=max(1, int(args.patience)),
                        restore_best_weights=True,
                    )
                )
            except Exception:
                callbacks = []

            history = model.fit(
                x_train,
                y_train,
                epochs=max(1, int(args.epochs)),
                batch_size=max(8, int(args.batch_size)),
                validation_data=(x_val, y_val),
                callbacks=callbacks,
                verbose=0,
            )
            val_loss, val_acc = model.evaluate(x_val, y_val, verbose=0)
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model.save(str(model_path))
            backend_used = "tensorflow"
        except KeyboardInterrupt:
            tf_reason = "KeyboardInterrupt during tensorflow training/import"
        except Exception as exc:
            tf_reason = f"{type(exc).__name__}: {exc}"
        if backend == "tensorflow" and backend_used != "tensorflow":
            report["status"] = "TRAIN_FAILED"
            report["reason"] = tf_reason or "tensorflow training failed"
            return 4, report

    if backend_used is None:
        try:
            import joblib
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import log_loss

            model = LogisticRegression(max_iter=300, class_weight="balanced", random_state=42)
            model.fit(x_train, y_train)
            proba = model.predict_proba(x_val)
            pred = (proba[:, 1] >= 0.5).astype(int)
            val_acc = float(np.mean(pred == y_val))
            try:
                val_loss = float(log_loss(y_val, proba, labels=[0, 1]))
            except Exception:
                val_loss = float(np.nan)

            if model_path.suffix.lower() in {".h5", ".keras"}:
                model_path = model_path.with_suffix(".pkl")
            model_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "backend": "sklearn",
                "model": model,
                "features": [str(c) for c in feature_names],
                "meta": {"trained_at_epoch": int(time.time()), "source": source},
            }
            joblib.dump(payload, str(model_path))
            backend_used = "sklearn"
        except Exception as exc:
            report["status"] = "TRAIN_FAILED"
            report["reason"] = f"sklearn_fallback_failed:{type(exc).__name__}:{exc}"
            if tf_reason:
                report["tensorflow_reason"] = tf_reason
            return 4, report

    fi_path = Path(args.feature_importance_path)
    try:
        _write_feature_importance(model, [str(c) for c in feature_names], fi_path)
    except Exception as exc:
        report["feature_importance_error"] = f"{type(exc).__name__}: {exc}"

    report["status"] = "TRAINED"
    report["backend_used"] = backend_used
    report["model_path"] = str(model_path)
    report["train_rows"] = int(len(y_train))
    report["val_rows"] = int(len(y_val))
    report["val_loss"] = float(val_loss) if val_loss is not None and np.isfinite(val_loss) else None
    report["val_accuracy"] = float(val_acc) if val_acc is not None else None
    report["epochs_ran"] = int(len(history.history.get("loss", []))) if history is not None else 1
    report["elapsed_sec"] = round(time.time() - start, 3)
    if tf_reason:
        report["tensorflow_reason"] = tf_reason

    if bool(args.register):
        try:
            from core.model_registry import activate_model, register_model

            metrics = {
                "val_accuracy": report["val_accuracy"],
                "val_loss": report["val_loss"],
                "train_rows": report["train_rows"],
                "val_rows": report["val_rows"],
            }
            governance = {
                "source": source,
                "features": [str(c) for c in feature_names],
                "target_positive_rate": report["target_positive_rate"],
            }
            register_model("microstructure", str(model_path), metrics=metrics, governance=governance)
            if bool(args.activate):
                activate_model("microstructure", str(model_path), metrics=metrics, governance=governance)
            report["registered"] = True
            report["activated"] = bool(args.activate)
        except Exception as exc:
            report["registered"] = False
            report["registry_error"] = f"{type(exc).__name__}: {exc}"

    return 0, report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Train microstructure model from tick/depth data.")
    parser.add_argument("--db-path", default=str(getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db"))))
    parser.add_argument("--csv-path", default="", help="Optional CSV/Parquet dataset path.")
    parser.add_argument("--model-path", default=str(getattr(cfg, "MICRO_MODEL_PATH", "models/microstructure_model.h5")))
    parser.add_argument("--feature-importance-path", default=str(logs_dir() / "micro_feature_importance.csv"))
    parser.add_argument("--horizon", type=int, default=2)
    parser.add_argument("--threshold", type=float, default=0.001)
    parser.add_argument("--min-rows", type=int, default=120)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--from-depth", action="store_true")
    parser.add_argument("--depth-tolerance-sec", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--backend",
        default=str(getattr(cfg, "MICRO_MODEL_TRAIN_BACKEND", "auto")),
        choices=["auto", "tensorflow", "sklearn"],
        help="Training backend. 'auto' tries tensorflow first, then sklearn fallback.",
    )
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--activate", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    code, report = _train(args)
    print(json.dumps(report, sort_keys=True))
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
