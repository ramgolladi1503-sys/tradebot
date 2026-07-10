import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from core.paths import logs_dir

REG_PATH = logs_dir() / "model_registry.json"
REJECTION_LEDGER_PATH = logs_dir() / "model_admission_rejections.jsonl"


def _hash_file(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load():
    if REG_PATH.exists():
        try:
            data = json.loads(REG_PATH.read_text())
            data.setdefault("active", {})
            data.setdefault("shadow", {})
            data.setdefault("history", {})
            data.setdefault("models", [])
            return data
        except Exception:
            pass
    return {"active": {}, "shadow": {}, "history": {}, "models": []}


def _save(data):
    REG_PATH.parent.mkdir(exist_ok=True)
    tmp_path = REG_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    tmp_path.replace(REG_PATH)


def _find_entry(data, model_type, path):
    path = str(path)
    for i, entry in enumerate(data.get("models", [])):
        if entry.get("type") == model_type and entry.get("path") == path:
            return i, entry
    return None, None


def _profitability_payload(metrics: dict | None) -> dict:
    metrics = metrics if isinstance(metrics, dict) else {}
    nested = metrics.get("profitability")
    if isinstance(nested, dict):
        return nested
    return {
        "expectancy": metrics.get("expectancy"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown": metrics.get("max_drawdown"),
        "net_pnl": metrics.get("net_pnl"),
        "win_rate": metrics.get("win_rate"),
    }


def validate_model_entry(entry):
    if not isinstance(entry, dict):
        return False, "MODEL_ENTRY_INVALID"
    if not entry.get("type") or not entry.get("path"):
        return False, "MODEL_ENTRY_MISSING_REQUIRED_FIELDS"
    if not entry.get("hash"):
        return False, "MODEL_ENTRY_MISSING_PROVENANCE"
    governance = entry.get("governance") or {}
    if not isinstance(governance, dict):
        return False, "MODEL_ENTRY_INVALID_GOVERNANCE"
    if not governance.get("features") and not governance.get("feature_list"):
        return False, "MODEL_ENTRY_MISSING_PROVENANCE"
    if not governance.get("training_window"):
        return False, "MODEL_ENTRY_MISSING_PROVENANCE"
    profitability = governance.get("profitability") or {}
    if profitability and not isinstance(profitability, dict):
        return False, "MODEL_ENTRY_INVALID_PROFITABILITY"
    if profitability and not any(profitability.get(k) is not None for k in ("expectancy", "profit_factor", "max_drawdown", "net_pnl", "win_rate")):
        return False, "MODEL_ENTRY_MISSING_PROFITABILITY_EVIDENCE"
    min_profit_factor = governance.get("min_profit_factor")
    min_expectancy = governance.get("min_expectancy")
    max_drawdown = governance.get("max_drawdown")
    if (min_profit_factor is not None or min_expectancy is not None or max_drawdown is not None) and not profitability:
        return False, "MODEL_ENTRY_MISSING_PROFITABILITY_EVIDENCE"
    if profitability:
        pf = profitability.get("profit_factor")
        expectancy = profitability.get("expectancy")
        drawdown = profitability.get("max_drawdown")
        if min_profit_factor is not None and pf is not None and float(pf) < float(min_profit_factor):
            return False, "MODEL_ENTRY_PROFITABILITY_FLOOR_NOT_MET"
        if min_expectancy is not None and expectancy is not None and float(expectancy) < float(min_expectancy):
            return False, "MODEL_ENTRY_EXPECTANCY_FLOOR_NOT_MET"
        if max_drawdown is not None and drawdown is not None and float(drawdown) < float(max_drawdown):
            return False, "MODEL_ENTRY_DRAWDOWN_FLOOR_NOT_MET"
    regime_coverage = governance.get("regime_coverage") or {}
    if regime_coverage:
        family = str(entry.get("type") or "").strip().lower()
        family_thresholds = governance.get("min_regime_coverage_by_family") or {}
        default_min = float(governance.get("min_regime_coverage", 0.2))
        min_coverage = float(family_thresholds.get(family, default_min)) if isinstance(family_thresholds, dict) else default_min
        if not isinstance(regime_coverage, dict):
            return False, "MODEL_ENTRY_INVALID_REGIME_COVERAGE"
        values = [float(v) for v in regime_coverage.values() if v is not None]
        if values and min(values) < min_coverage:
            return False, "MODEL_ENTRY_INSUFFICIENT_REGIME_COVERAGE"
    return True, "ok"


def admit_model_entry(entry):
    ok, reason = validate_model_entry(entry)
    if not ok:
        raise ValueError(reason)
    return entry


def verify_admission_report(report: dict) -> tuple[bool, str]:
    if not isinstance(report, dict):
        return False, "REPORT_INVALID"
    report_hash = report.get("report_hash")
    if not report_hash:
        return False, "REPORT_MISSING_HASH"
    check = hashlib.sha256(
        json.dumps({k: v for k, v in report.items() if k != "report_hash"}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if check != report_hash:
        return False, "REPORT_HASH_MISMATCH"
    path_hash = _hash_file(report.get("path"))
    if path_hash and report.get("hash") and path_hash != report.get("hash"):
        return False, "ARTIFACT_HASH_MISMATCH"
    return True, "ok"


def build_admission_report(
    *,
    model_type: str,
    path: str | Path,
    status: str,
    governance: dict | None,
    metrics: dict | None = None,
    checks: dict | None = None,
    reason: str | None = None,
) -> dict:
    governance = governance or {}
    entry = {
        "type": str(model_type),
        "path": str(path),
        "hash": _hash_file(path),
        "governance": governance,
    }
    ok, reason_code = validate_model_entry(entry)
    walk_forward = governance.get("walk_forward") or {}
    selection = walk_forward.get("selection") if isinstance(walk_forward, dict) else None
    profitability = _profitability_payload(metrics)
    if ok and isinstance(walk_forward, dict) and walk_forward.get("status") in {"NO_ADMISSIBLE_MODEL", "ERROR", "FAILED"}:
        ok = False
        reason_code = f"WALK_FORWARD_{str(walk_forward.get('status')).upper()}"
    if ok and isinstance(selection, dict) and selection.get("status") != "SELECTED":
        ok = False
        reason_code = "WALK_FORWARD_NO_SELECTION"
    if ok:
        floor_pf = governance.get("min_profit_factor")
        floor_exp = governance.get("min_expectancy")
        floor_dd = governance.get("max_drawdown")
        if floor_pf is not None and profitability.get("profit_factor") is not None and float(profitability["profit_factor"]) < float(floor_pf):
            ok = False
            reason_code = "MODEL_ENTRY_PROFITABILITY_FLOOR_NOT_MET"
        if ok and floor_exp is not None and profitability.get("expectancy") is not None and float(profitability["expectancy"]) < float(floor_exp):
            ok = False
            reason_code = "MODEL_ENTRY_EXPECTANCY_FLOOR_NOT_MET"
        if ok and floor_dd is not None and profitability.get("max_drawdown") is not None and float(profitability["max_drawdown"]) < float(floor_dd):
            ok = False
            reason_code = "MODEL_ENTRY_DRAWDOWN_FLOOR_NOT_MET"
    report = {
        "schema_version": 1,
        "timestamp": _now_iso(),
        "model_type": str(model_type),
        "path": str(path),
        "hash": entry["hash"],
        "status": str(status),
        "admitted": bool(ok),
        "reason": reason or reason_code,
        "metrics": metrics or {},
        "profitability": profitability,
        "governance": governance,
        "checks": checks or {},
        "selection": selection if selection is not None else (walk_forward.get("selected") if isinstance(walk_forward, dict) else None),
    }
    report["report_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in report.items() if k != "report_hash"}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    if not ok and not reason:
        report["reason"] = reason_code
    return report


def write_admission_report(report: dict, output_path: str | Path | None = None) -> Path:
    out = Path(output_path) if output_path else logs_dir() / "model_admission_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return out


def write_rejection_artifact(report: dict, output_path: str | Path | None = None) -> Path:
    out = Path(output_path) if output_path else logs_dir() / "model_admission_rejection.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    return out


def append_rejection_ledger(report: dict, output_path: str | Path | None = None) -> Path:
    out = Path(output_path) if output_path else REJECTION_LEDGER_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(report, sort_keys=True) + "\n")
    return out


def register_model(model_type, path, metrics=None, governance=None, status="candidate"):
    metrics = metrics or {}
    governance = dict(governance or {})
    profitability = _profitability_payload(metrics)
    if profitability and "profitability" not in governance:
        if any(v is not None for v in profitability.values()):
            governance["profitability"] = profitability
    data = _load()
    entry = {
        "type": model_type,
        "path": str(path),
        "hash": _hash_file(path),
        "metrics": metrics,
        "governance": governance,
        "status": status,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    admit_model_entry(entry)
    report = build_admission_report(
        model_type=model_type,
        path=path,
        status=status,
        governance=governance or {"features": ["registry"], "training_window": {"rows": int((metrics or {}).get("train_rows", 0) or 0)}},
        metrics=metrics,
        checks={"registry_write": True},
    )
    ok, reason = verify_admission_report(report)
    if not ok:
        raise ValueError(reason)
    if status in {"active", "shadow"}:
        walk_forward = (governance or {}).get("walk_forward") if isinstance(governance, dict) else None
        if not isinstance(walk_forward, dict) or walk_forward.get("status") != "SELECTED":
            raise ValueError("WALK_FORWARD_NO_SELECTION")
    idx, _ = _find_entry(data, model_type, path)
    if idx is None:
        data["models"].append(entry)
    else:
        data["models"][idx].update(entry)
    _save(data)
    return entry


def update_model_metrics(model_type, path, metrics=None, governance=None):
    data = _load()
    idx, entry = _find_entry(data, model_type, path)
    if idx is None:
        entry = register_model(model_type, path, metrics=metrics, governance=governance)
        return entry
    if metrics:
        entry.setdefault("metrics", {}).update(metrics)
    if governance:
        entry.setdefault("governance", {}).update(governance)
    admit_model_entry(entry)
    data["models"][idx] = entry
    _save(data)
    return entry


def activate_model(model_type, path, metrics=None, governance=None):
    metrics = metrics or {}
    governance = dict(governance or {})
    profitability = _profitability_payload(metrics)
    if profitability and "profitability" not in governance:
        if any(v is not None for v in profitability.values()):
            governance["profitability"] = profitability
    entry = {
        "type": model_type,
        "path": str(path),
        "hash": _hash_file(path),
        "metrics": metrics,
        "governance": governance,
    }
    admit_model_entry(entry)
    report = build_admission_report(
        model_type=model_type,
        path=path,
        status="active",
        governance=governance or {"features": ["registry"], "training_window": {"rows": int((metrics or {}).get("train_rows", 0) or 0)}},
        metrics=metrics,
        checks={"registry_write": True},
    )
    ok, reason = verify_admission_report(report)
    if not ok:
        raise ValueError(reason)
    walk_forward = (governance or {}).get("walk_forward") if isinstance(governance, dict) else None
    if not isinstance(walk_forward, dict) or walk_forward.get("status") != "SELECTED":
        raise ValueError("WALK_FORWARD_NO_SELECTION")
    data = _load()
    prev = data.get("active", {}).get(model_type)
    if prev and prev != str(path):
        data.setdefault("history", {}).setdefault(model_type, []).append(prev)
    data["active"][model_type] = str(path)
    update_model_metrics(model_type, path, metrics=metrics, governance=governance)
    idx, entry = _find_entry(data, model_type, path)
    if idx is not None:
        entry["status"] = "active"
        data["models"][idx] = entry
    _save(data)
    return data["active"]


def set_shadow(model_type, path, metrics=None, governance=None):
    metrics = metrics or {}
    governance = dict(governance or {})
    profitability = _profitability_payload(metrics)
    if profitability and "profitability" not in governance:
        if any(v is not None for v in profitability.values()):
            governance["profitability"] = profitability
    entry = {
        "type": model_type,
        "path": str(path),
        "hash": _hash_file(path),
        "metrics": metrics,
        "governance": governance,
    }
    admit_model_entry(entry)
    report = build_admission_report(
        model_type=model_type,
        path=path,
        status="shadow",
        governance=governance or {"features": ["registry"], "training_window": {"rows": int((metrics or {}).get("train_rows", 0) or 0)}},
        metrics=metrics,
        checks={"registry_write": True},
    )
    ok, reason = verify_admission_report(report)
    if not ok:
        raise ValueError(reason)
    walk_forward = (governance or {}).get("walk_forward") if isinstance(governance, dict) else None
    if not isinstance(walk_forward, dict) or walk_forward.get("status") != "SELECTED":
        raise ValueError("WALK_FORWARD_NO_SELECTION")
    data = _load()
    data["shadow"][model_type] = str(path)
    update_model_metrics(model_type, path, metrics=metrics, governance=governance)
    idx, entry = _find_entry(data, model_type, path)
    if idx is not None:
        entry["status"] = "shadow"
        data["models"][idx] = entry
    _save(data)
    return data["shadow"]


def rollback_model(model_type, steps=1):
    data = _load()
    history = data.get("history", {}).get(model_type, [])
    if not history or steps <= 0 or len(history) < steps:
        return None
    new_path = history[-steps]
    data["history"][model_type] = history[:-steps]
    data["active"][model_type] = new_path
    idx, entry = _find_entry(data, model_type, new_path)
    if idx is not None:
        entry["status"] = "active"
        data["models"][idx] = entry
    _save(data)
    return new_path


def prune_history(model_type, keep_n=3):
    data = _load()
    history = data.get("history", {}).get(model_type, [])
    if keep_n is None or keep_n <= 0:
        return history
    if len(history) <= keep_n:
        return history
    data["history"][model_type] = history[-keep_n:]
    _save(data)
    return data["history"][model_type]


def get_active(model_type):
    data = _load()
    return data.get("active", {}).get(model_type)


def get_shadow(model_type):
    data = _load()
    return data.get("shadow", {}).get(model_type)


def get_active_entry(model_type):
    data = _load()
    path = data.get("active", {}).get(model_type)
    if not path:
        return None
    _, entry = _find_entry(data, model_type, path)
    return entry


def get_shadow_entry(model_type):
    data = _load()
    path = data.get("shadow", {}).get(model_type)
    if not path:
        return None
    _, entry = _find_entry(data, model_type, path)
    return entry


def list_models(model_type=None):
    data = _load()
    models = data.get("models", [])
    if not model_type:
        return models
    return [m for m in models if m.get("type") == model_type]
