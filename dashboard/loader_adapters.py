from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import config as cfg
from core.paths import logs_dir
from dashboard.loaders import load_depth_vm, load_execution_vm, load_recon_vm


def load_execution_analytics(path: Path | None = None) -> dict[str, Any]:
    target = path or (logs_dir() / "execution_analytics.json")
    vm = load_execution_vm(target)
    out = dict(vm.payload)
    out.setdefault("status", vm.status)
    out.setdefault("path", str(target))
    if vm.message:
        out.setdefault("message", vm.message)
    return out


def load_reconciliation_summary(path: Path | None = None) -> dict[str, Any]:
    target = path or (logs_dir() / "recon.json")
    vm = load_recon_vm(target)
    out = dict(vm.payload)
    out.setdefault("status", vm.status)
    out.setdefault("path", str(target))
    if vm.message:
        out.setdefault("message", vm.message)
    return out


def load_depth_status(db_path: str | Path | None = None) -> dict[str, Any]:
    db = Path(str(db_path or getattr(cfg, "TRADE_DB_PATH", "")))
    vm = load_depth_vm(db)
    out = asdict(vm)
    out["db_path"] = str(vm.db_path) if vm.db_path else None
    out["rows"] = int(vm.row_count)
    out.pop("row_count", None)
    return out
