from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from config import config as cfg
from config.profile import get_option_filter_profile, get_runtime_profile
from core.events import write_json_atomic
from core.paths import logs_dir
from core.time_utils import now_utc_epoch, utc_now

_SCHEMA_VERSION = 1
_DEFAULT_KEY_FILES = (
    "config/config.py",
    "config/profile.py",
    "core/freshness_policy.py",
    "core/readiness_gate.py",
    "core/gating.py",
)
_CRITICAL_CONFIG_KEYS = (
    "DESK_ID",
    "RISK_PROFILE",
    "MAX_RISK_PER_TRADE_PCT",
    "MAX_DAILY_LOSS_PCT",
    "MAX_OPEN_RISK_PCT",
    "MAX_TRADES_PER_DAY",
    "LIVE_PILOT_MODE",
    "LIVE_MAX_LOTS",
    "LIVE_MAX_TRADES_PER_DAY",
    "LIVE_MAX_SPREAD_PCT",
    "LIVE_MAX_QUOTE_AGE_SEC",
    "MANUAL_APPROVAL",
    "READINESS_ENFORCE_ON_EXEC",
    "GOV_GATE_REQUIRE_AUTH",
    "SURVIVAL_GATES_ENABLED",
    "MAX_DAILY_DRAWDOWN",
    "MAX_CONSECUTIVE_LOSSES",
    "VOLATILITY_SIZING_MULTIPLIER",
    "AUTO_FLATTEN_ON_BREACH",
    "CONSERVATIVE_PROFIT_CAPTURE_ENABLE",
    "CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_TRIGGER_PCT",
    "CONSERVATIVE_PROFIT_CAPTURE_LOCKIN_DRAWDOWN_PCT",
    "CONSERVATIVE_PROFIT_CAPTURE_RISK_MULT",
    "CONSERVATIVE_PROFIT_CAPTURE_SOFT_HALT_FRACTION",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def approved_config_path() -> Path:
    explicit = str(getattr(cfg, "CONFIG_APPROVAL_PATH", "") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return logs_dir() / "approved_config.json"


def _key_files_configured() -> list[str]:
    raw = str(getattr(cfg, "CONFIG_APPROVAL_KEY_FILES", "") or "").strip()
    if not raw:
        return list(_DEFAULT_KEY_FILES)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _resolve_key_file(path_text: str) -> Path:
    candidate = Path(path_text).expanduser()
    if candidate.is_absolute():
        return candidate
    return (_repo_root() / candidate).resolve()


def _hash_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _critical_config_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _CRITICAL_CONFIG_KEYS:
        out[key] = _json_safe(getattr(cfg, key, None))
    return out


def _live_profile_snapshot() -> dict[str, Any]:
    runtime_profile = get_runtime_profile(mode="LIVE")
    option_profile = get_option_filter_profile(
        mode="LIVE",
        base_max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.03),
        base_min_volume_filter=getattr(cfg, "MIN_VOLUME_FILTER", 500),
    )
    return {
        "runtime_profile": _json_safe(runtime_profile.to_dict()),
        "option_filter_profile": _json_safe(option_profile.to_dict()),
    }


def _key_file_snapshot() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = _repo_root()
    for configured in _key_files_configured():
        path = _resolve_key_file(configured)
        digest = _hash_file(path)
        rel = None
        try:
            rel = str(path.relative_to(root))
        except Exception:
            rel = str(path)
        rows.append(
            {
                "configured": str(configured),
                "path": str(path),
                "repo_relative_path": rel,
                "exists": bool(path.exists()),
                "sha256": digest,
            }
        )
    return rows


def compute_config_fingerprint(*, desk_id: str | None = None) -> dict[str, Any]:
    desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "desk_id": desk,
        "live_profile": _live_profile_snapshot(),
        "critical_config": _critical_config_snapshot(),
        "key_files": _key_file_snapshot(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "config_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "payload": payload,
    }


def _load_approved(path: Path | None = None) -> dict[str, Any]:
    target = path or approved_config_path()
    if not target.exists():
        return {"schema_version": _SCHEMA_VERSION, "records": {}}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": _SCHEMA_VERSION, "records": {}}
    if not isinstance(raw, dict):
        return {"schema_version": _SCHEMA_VERSION, "records": {}}
    records = raw.get("records")
    if not isinstance(records, dict):
        records = {}
    return {
        "schema_version": int(raw.get("schema_version") or _SCHEMA_VERSION),
        "records": dict(records),
    }


def approve_current_config(*, desk_id: str | None = None, actor: str | None = None, path: Path | None = None) -> dict[str, Any]:
    target = path or approved_config_path()
    desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    fingerprint = compute_config_fingerprint(desk_id=desk)
    state = _load_approved(target)
    records = dict(state.get("records") or {})
    approved_ts_epoch = float(now_utc_epoch())
    records[desk] = {
        "desk_id": desk,
        "config_hash": str(fingerprint["config_hash"]),
        "approved_ts_epoch": approved_ts_epoch,
        "approved_ts_iso": utc_now().isoformat().replace("+00:00", "Z"),
        "approved_by": str(actor or "manual"),
        "key_files": list(fingerprint["payload"].get("key_files") or []),
    }
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "records": records,
    }
    write_json_atomic(target, payload)
    return {
        "ok": True,
        "desk_id": desk,
        "config_hash": str(fingerprint["config_hash"]),
        "path": str(target),
    }


def check_config_approval(*, desk_id: str | None = None, path: Path | None = None) -> dict[str, Any]:
    target = path or approved_config_path()
    desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    fingerprint = compute_config_fingerprint(desk_id=desk)
    state = _load_approved(target)
    record = dict((state.get("records") or {}).get(desk) or {})
    approved_hash = str(record.get("config_hash") or "").strip()
    current_hash = str(fingerprint["config_hash"])
    if not approved_hash:
        return {
            "ok": False,
            "desk_id": desk,
            "reason": "approval_missing",
            "approved_hash": None,
            "current_hash": current_hash,
            "path": str(target),
        }
    if approved_hash != current_hash:
        return {
            "ok": False,
            "desk_id": desk,
            "reason": "approval_hash_mismatch",
            "approved_hash": approved_hash,
            "current_hash": current_hash,
            "path": str(target),
        }
    return {
        "ok": True,
        "desk_id": desk,
        "reason": "ok",
        "approved_hash": approved_hash,
        "current_hash": current_hash,
        "path": str(target),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve/check immutable live configuration hash.")
    sub = parser.add_subparsers(dest="command")

    approve = sub.add_parser("approve", help="Approve current live config hash.")
    approve.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    approve.add_argument("--actor", default="manual")

    check = sub.add_parser("check", help="Check current hash against approved hash.")
    check.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = str(args.command or "check")

    if command == "approve":
        result = approve_current_config(desk_id=args.desk, actor=args.actor)
        print(
            json.dumps(
                {
                    "ok": True,
                    "action": "approve",
                    "desk_id": result["desk_id"],
                    "config_hash": result["config_hash"],
                    "path": result["path"],
                },
                ensure_ascii=True,
            )
        )
        return 0

    result = check_config_approval(desk_id=getattr(args, "desk", None))
    print(json.dumps(result, ensure_ascii=True))
    return 0 if bool(result.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
