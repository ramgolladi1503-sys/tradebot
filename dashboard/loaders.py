from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from config import config as cfg
from core.paths import desk_logs_dir, desks_dir, logs_dir, trade_db_path
from core.snapshot_schema import compute_snapshot_id
from dashboard.models import (
    ArtifactVM,
    DepthVM,
    EventsVM,
    ExecutionVM,
    FeedVM,
    GeminiVM,
    HealthGateVM,
    ReconVM,
    RiskVM,
)


def _desk_id_text(desk: str | None) -> str:
    return str(desk or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")


def _candidate_log_paths(desk_id: str, filename: str) -> list[Path]:
    # Desk-specific file first; shared runtime fallback second.
    return [desk_logs_dir(desk_id) / filename, logs_dir() / filename]


def _select_path(candidates: Iterable[Path]) -> Path:
    values = list(candidates)
    for path in values:
        if path.exists():
            return path
    return values[0]


def _load_json_payload(path: Path, *, missing_message: str) -> tuple[str, str | None, dict[str, Any]]:
    if not path.exists():
        return "missing", missing_message, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return "error", f"parse_error:{exc}", {}
    if isinstance(payload, dict):
        status = str(payload.get("status") or "ok")
        message = payload.get("message")
        return status, (str(message) if message else None), payload
    return "error", "payload_not_object", {}


def _load_jsonl_rows(path: Path) -> tuple[str, str | None, list[dict[str, Any]]]:
    if not path.exists():
        return "missing", "events artifact missing", []
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            bad_rows += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    if not rows and bad_rows > 0:
        return "error", f"events_parse_error:bad_rows={bad_rows}", []
    if not rows:
        return "empty", "no events found", []
    if bad_rows > 0:
        return "ok", f"events_parse_partial:bad_rows={bad_rows}", rows
    return "ok", None, rows


def _artifact_vm(
    vm_cls: type[ArtifactVM],
    desk_id: str,
    path: Path,
    missing_message: str,
) -> ArtifactVM:
    status, message, payload = _load_json_payload(path, missing_message=missing_message)
    return vm_cls(desk_id=desk_id, status=status, path=path, message=message, payload=payload)


def _load_market_snapshot_payload(desk_id: str, runtime_payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    inline = runtime_payload.get("market_snapshot")
    if isinstance(inline, dict):
        return dict(inline), None

    snapshot_path_text = str(runtime_payload.get("snapshot_path") or "").strip()
    candidates: list[Path] = []
    if snapshot_path_text:
        candidates.append(Path(snapshot_path_text))
    candidates.extend(
        [
            desk_logs_dir(desk_id) / "market_snapshot_latest.json",
            logs_dir() / "market_snapshot_latest.json",
        ]
    )
    snapshot_path = _select_path(candidates)
    if not snapshot_path.exists():
        return {}, None
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"snapshot_parse_error:{exc}"
    if not isinstance(payload, dict):
        return {}, "snapshot_payload_not_object"
    return dict(payload), None


def _build_feed_payload_from_snapshot(
    desk_id: str,
    runtime_payload: dict[str, Any],
) -> tuple[str, str | None, dict[str, Any]]:
    snapshot, snapshot_error = _load_market_snapshot_payload(desk_id, runtime_payload)
    if snapshot_error:
        return "error", snapshot_error, {}
    if not snapshot:
        return "", None, {}

    try:
        from core.contracts.invariants import assert_invariants
        from core.health_gate import evaluate_runtime_health

        assert_invariants(snapshot, stage="dashboard_loader")
        runtime_feed = runtime_payload.get("feed") if isinstance(runtime_payload.get("feed"), dict) else {}
        feed_connected_raw = runtime_feed.get("ws_connected")
        if isinstance(feed_connected_raw, bool):
            feed_connected = feed_connected_raw
        else:
            # Unknown feed connectivity must not hard-fail the loader.
            feed_connected = True
        db_ok_raw = runtime_payload.get("db_ok")
        db_ok = bool(db_ok_raw) if db_ok_raw is not None else True
        runtime_eval = evaluate_runtime_health(
            snapshot,
            feed_connected=feed_connected,
            db_ok=db_ok,
        )
    except Exception as exc:
        return "error", f"snapshot_runtime_eval_error:{type(exc).__name__}", {}

    snapshot_id = str(snapshot.get("snapshot_id") or "").strip()
    if not snapshot_id:
        snapshot_id = compute_snapshot_id(snapshot)
    freshness = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    payload = dict(runtime_payload)
    payload["snapshot_id"] = snapshot_id
    payload["freshness_source"] = "snapshot_v1"
    payload["freshness"] = {
        "max_tick_age_sec": freshness.get("max_tick_age_sec"),
        "sla_threshold_sec": freshness.get("sla_threshold_sec"),
        "stale_tokens_count": freshness.get("stale_tokens_count"),
    }
    payload["runtime_health"] = runtime_eval
    payload["status_light"] = "OK" if bool(runtime_eval.get("ok")) else "BLOCKED"
    status = "ok" if bool(runtime_eval.get("ok")) else "error"
    message = None
    if not bool(runtime_eval.get("ok")):
        blockers = runtime_eval.get("blockers") if isinstance(runtime_eval.get("blockers"), list) else []
        if blockers:
            codes = [str((item or {}).get("code") or "UNKNOWN") for item in blockers]
            message = f"runtime_health_blocked:{'|'.join(codes)}"
        else:
            message = "runtime_health_blocked"
    return status, message, payload


def load_health_gate_report(desk: str | None = None) -> HealthGateVM:
    desk_id = _desk_id_text(desk)
    path = _select_path(_candidate_log_paths(desk_id, "health_gate_report.json"))
    return _artifact_vm(HealthGateVM, desk_id, path, "health gate report missing")


def load_events(desk: str | None = None) -> EventsVM:
    desk_id = _desk_id_text(desk)
    path = _select_path(_candidate_log_paths(desk_id, "events.jsonl"))
    status, message, rows = _load_jsonl_rows(path)
    if rows:
        rows = [
            row
            for row in rows
            if str((row.get("payload") or {}).get("desk_id") or desk_id).upper() == desk_id.upper()
            or not isinstance(row.get("payload"), dict)
        ]
        if not rows:
            status = "empty"
            message = message or "no events for desk"
    return EventsVM(desk_id=desk_id, status=status, path=path, message=message, rows=rows)


def load_reconciliation(desk: str | None = None) -> ReconVM:
    desk_id = _desk_id_text(desk)
    path = _select_path(_candidate_log_paths(desk_id, "recon.json"))
    return _artifact_vm(ReconVM, desk_id, path, "reconciliation artifact missing")


def load_execution_analytics(desk: str | None = None) -> ExecutionVM:
    desk_id = _desk_id_text(desk)
    path = _select_path(_candidate_log_paths(desk_id, "execution_analytics.json"))
    return _artifact_vm(ExecutionVM, desk_id, path, "execution analytics artifact missing")


def load_feed_state(desk: str | None = None) -> FeedVM:
    desk_id = _desk_id_text(desk)
    candidates = [
        *_candidate_log_paths(desk_id, "runtime_health_latest.json"),
        *_candidate_log_paths(desk_id, "feed_state.json"),
        *_candidate_log_paths(desk_id, "feed_health.json"),
    ]
    path = _select_path(candidates)
    status, message, payload = _load_json_payload(path, missing_message="feed artifact missing")
    if status in {"missing", "error"}:
        return FeedVM(desk_id=desk_id, status=status, path=path, message=message, payload=payload)

    snapshot_status, snapshot_message, snapshot_payload = _build_feed_payload_from_snapshot(desk_id, payload)
    if snapshot_status:
        return FeedVM(
            desk_id=desk_id,
            status=snapshot_status,
            path=path,
            message=snapshot_message,
            payload=snapshot_payload,
        )

    # Legacy fallback: keep informational only and explicitly marked.
    legacy_payload = dict(payload or {})
    legacy_payload["freshness_source"] = "legacy_runtime_health"
    legacy_payload["legacy_freshness"] = {
        "ltp_age_sec": ((legacy_payload.get("feed") or {}).get("ltp_age_sec")),
        "depth_age_sec": ((legacy_payload.get("feed") or {}).get("depth_age_sec")),
        "reasons": list(((legacy_payload.get("feed") or {}).get("reasons") or [])),
    }
    legacy_payload["status_light"] = "UNKNOWN_LEGACY"
    return FeedVM(desk_id=desk_id, status=status, path=path, message=message, payload=legacy_payload)


def load_risk_state(desk: str | None = None) -> RiskVM:
    desk_id = _desk_id_text(desk)
    path = _select_path(_candidate_log_paths(desk_id, "risk_monitor.json"))
    return _artifact_vm(RiskVM, desk_id, path, "risk artifact missing")


def load_depth_snapshot(desk: str | None = None) -> DepthVM:
    desk_id = _desk_id_text(desk)
    db_path = trade_db_path(desk_id).expanduser()
    if not db_path.exists():
        return DepthVM(
            desk_id=desk_id,
            status="missing",
            db_path=db_path,
            message=f"depth db missing: {db_path}",
            columns=[],
            row_count=0,
            payload={"desk_data_dir": str(desks_dir(desk_id))},
        )
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM depth_snapshots")
            row_count = int((cur.fetchone() or [0])[0] or 0)
            if row_count <= 0:
                return DepthVM(
                    desk_id=desk_id,
                    status="empty",
                    db_path=db_path,
                    message="no depth snapshots captured",
                    columns=[],
                    row_count=0,
                    payload={},
                )
            cur = conn.execute(
                "SELECT * FROM depth_snapshots ORDER BY timestamp DESC LIMIT 1"
            )
            columns = [str(col[0]) for col in (cur.description or [])]
            latest = cur.fetchone()
    except sqlite3.OperationalError as exc:
        msg = str(exc)
        if "no such table" in msg.lower():
            return DepthVM(
                desk_id=desk_id,
                status="empty",
                db_path=db_path,
                message="no depth snapshots captured",
                columns=[],
                row_count=0,
                payload={},
            )
        return DepthVM(
            desk_id=desk_id,
            status="error",
            db_path=db_path,
            message=f"depth_query_error:{exc}",
            columns=[],
            row_count=0,
            payload={},
        )
    except Exception as exc:
        return DepthVM(
            desk_id=desk_id,
            status="error",
            db_path=db_path,
            message=f"depth_query_error:{exc}",
            columns=[],
            row_count=0,
            payload={},
        )
    latest_payload = {}
    if latest is not None and columns:
        latest_payload = {columns[idx]: latest[idx] for idx in range(min(len(columns), len(latest)))}
    return DepthVM(
        desk_id=desk_id,
        status="ok",
        db_path=db_path,
        message=None,
        columns=columns,
        row_count=row_count,
        payload=latest_payload,
    )


def load_gemini_state(desk: str | None = None) -> GeminiVM:
    desk_id = _desk_id_text(desk)
    advice_path = _select_path(_candidate_log_paths(desk_id, "gpt_advice.jsonl"))
    usage_path = _select_path(_candidate_log_paths(desk_id, "gpt_usage.json"))
    status, message, payload = _load_json_payload(usage_path, missing_message="gpt usage artifact missing")
    payload = dict(payload)
    payload["advice_path"] = str(advice_path)
    payload["usage_path"] = str(usage_path)
    payload["provider"] = str(payload.get("provider") or "")
    payload["model"] = str(payload.get("model") or "")
    return GeminiVM(
        desk_id=desk_id,
        status=status,
        path=usage_path,
        message=message,
        payload=payload,
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
    )


# Backward-compatible dashboard callsites.
def load_execution_vm(path: Path) -> ExecutionVM:
    desk_id = _desk_id_text(None)
    return _artifact_vm(ExecutionVM, desk_id, Path(path), "execution analytics artifact missing")


def load_recon_vm(path: Path) -> ReconVM:
    desk_id = _desk_id_text(None)
    return _artifact_vm(ReconVM, desk_id, Path(path), "reconciliation artifact missing")


def load_feed_vm(path: Path) -> FeedVM:
    desk_id = _desk_id_text(None)
    return _artifact_vm(FeedVM, desk_id, Path(path), "feed artifact missing")


def load_risk_vm(path: Path) -> RiskVM:
    desk_id = _desk_id_text(None)
    return _artifact_vm(RiskVM, desk_id, Path(path), "risk artifact missing")


def load_depth_vm(db_path: Path, fetch_fn=None) -> DepthVM:
    # Retain signature used by existing runtime + tests. Optional fetch_fn preserved
    # for deterministic test stubbing.
    if fetch_fn is not None:
        try:
            cols, rows = fetch_fn(1)
        except Exception as exc:
            return DepthVM(
                desk_id=_desk_id_text(None),
                status="error",
                db_path=Path(db_path),
                message=f"depth_fetch_error:{exc}",
                columns=[],
                row_count=0,
                payload={},
            )
        if not rows:
            return DepthVM(
                desk_id=_desk_id_text(None),
                status="empty",
                db_path=Path(db_path),
                message="no depth snapshots captured",
                columns=list(cols),
                row_count=0,
                payload={},
            )
        return DepthVM(
            desk_id=_desk_id_text(None),
            status="ok",
            db_path=Path(db_path),
            message=None,
            columns=list(cols),
            row_count=len(rows),
            payload={},
        )
    return load_depth_snapshot(_desk_id_text(None))
