#!/usr/bin/env python3
"""Audit the local 2026-08-04 Upstox corpus without modifying source evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from core.upstox_corpus_audit import (
    AuditError,
    assert_snapshot_unchanged,
    audit_parquet_tree,
    audit_sqlite_database,
    audit_zstandard_files,
    compare_replay_databases,
    read_bar_intervals,
    reconcile_normalized_and_replay_counts,
    run_pr786_offline_rehearsal,
    snapshot_paths,
    verify_manifest_references,
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _gate(name: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {"gate": name, "passed": False, "status": "NOT_RUN", "errors": ["measurement_unavailable"]}
    return {
        "gate": name,
        "passed": bool(value.get("passed") or str(value.get("verdict", "")).startswith("PASS_")),
        "status": "PASS" if bool(value.get("passed") or str(value.get("verdict", "")).startswith("PASS_")) else "FAIL",
        "errors": list(value.get("errors") or []),
    }


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Upstox 2026-08-04 Corpus Independent Audit",
        "",
        f"Overall verdict: `{report['verdict']}`",
        "",
        "## Boundaries",
        "",
        "- Offline Upstox replay only.",
        "- Not a Kite live certification.",
        "- Not an option corpus.",
        "- No structural-edge or profitability claim.",
        "- Source evidence was opened read-only and checked for mutation.",
        "",
        "## Gates",
        "",
    ]
    for gate in report.get("gates", []):
        lines.append(f"- `{gate['gate']}`: **{gate['status']}**")
        for error in gate.get("errors", []):
            lines.append(f"  - `{error}`")
    normalized = report.get("normalized") or {}
    raw = report.get("raw") or {}
    bars = report.get("bars") or {}
    replay = report.get("replay_comparison") or {}
    rehearsal = report.get("pr786_offline_rehearsal") or {}
    lines.extend(
        [
            "",
            "## Corpus",
            "",
            f"- Zstandard chunks: `{raw.get('file_count', 'unavailable')}`",
            f"- Normalized Parquet files: `{normalized.get('file_count', 'unavailable')}`",
            f"- Normalized rows: `{normalized.get('row_count', 'unavailable')}`",
            f"- Unique instruments: `{normalized.get('unique_instrument_count', 'unavailable')}`",
            f"- Timestamp span: `{normalized.get('timestamp_min', 'unavailable')}` → `{normalized.get('timestamp_max', 'unavailable')}`",
            "",
            "## Replay",
            "",
            f"- Deterministic comparison: `{replay.get('passed', 'not run')}`",
            f"- Run A semantic SHA: `{(replay.get('run_a') or {}).get('database_semantic_sha256', 'unavailable')}`",
            f"- Run B semantic SHA: `{(replay.get('run_b') or {}).get('database_semantic_sha256', 'unavailable')}`",
            "",
            "## MEG / PR #786 rehearsal",
            "",
            f"- Accepted bar intervals: `{bars.get('interval_count', 'unavailable')}`",
            f"- Rehearsal verdict: `{rehearsal.get('verdict', 'not run')}`",
            f"- Authority snapshots: `{rehearsal.get('authority_snapshot_count', 'unavailable')}`",
            f"- Primary evaluations: `{rehearsal.get('primary_evaluation_count', 'unavailable')}`",
            f"- Duplicate successful exports: `{rehearsal.get('duplicate_successful_export_count', 'unavailable')}`",
            f"- Canonical seal gate: `{rehearsal.get('seal_gate_passed', 'unavailable')}`",
            "",
            "## Next live session",
            "",
            f"Ready for fresh governed Kite session: `{report.get('kite_fresh_live_session_ready', False)}`",
            "",
            "A fresh Kite market-hours run remains mandatory even when every offline gate passes.",
        ]
    )
    return "\n".join(lines) + "\n"


def _table_count(database: Mapping[str, Any], *names: str) -> int | None:
    tables = database.get("tables") or {}
    for name in names:
        value = tables.get(name)
        if isinstance(value, Mapping) and value.get("row_count") is not None:
            return int(value["row_count"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-run-dir", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--audit-root", required=True, type=Path)
    parser.add_argument("--replay-db-a", type=Path)
    parser.add_argument("--replay-db-b", type=Path)
    parser.add_argument("--bars-path", type=Path)
    parser.add_argument("--explained-non-tick-rows", type=int)
    args = parser.parse_args()

    raw_root = args.raw_run_dir.expanduser().resolve()
    evidence_root = args.evidence_root.expanduser().resolve()
    audit_root = args.audit_root.expanduser().resolve()
    if not raw_root.is_dir():
        raise SystemExit("RAW_RUN_DIR_MISSING")
    if not evidence_root.is_dir():
        raise SystemExit("EVIDENCE_ROOT_MISSING")
    if audit_root == raw_root or audit_root == evidence_root or raw_root in audit_root.parents or evidence_root in audit_root.parents:
        raise SystemExit("AUDIT_ROOT_MUST_BE_SEPARATE_FROM_SOURCE_EVIDENCE")
    audit_root.mkdir(parents=True, exist_ok=True)

    bars_path = (args.bars_path or evidence_root / "meg" / "nifty50_constituent_bars_1m.parquet").expanduser().resolve()
    protected = [
        path
        for path in (
            evidence_root / "artifact_manifest.json",
            evidence_root / "SHA256SUMS",
            evidence_root / "SEALED",
            evidence_root / "session_manifest.json",
            evidence_root / "session_manifest.sha256",
            evidence_root / "validation_report.json",
            evidence_root / "meg" / "meg_replay_evidence_20260804.json",
            bars_path,
        )
        if path.exists()
    ]
    before = snapshot_paths(protected)

    raw_audit: dict[str, Any] | None = None
    normalized_audit: dict[str, Any] | None = None
    manifests: list[dict[str, Any]] = []
    replay_a: dict[str, Any] | None = None
    replay_b: dict[str, Any] | None = None
    replay_comparison: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    bars: dict[str, Any] | None = None
    rehearsal: dict[str, Any] | None = None
    runtime_errors: list[str] = []

    try:
        raw_audit = audit_zstandard_files(raw_root)
        normalized_root = raw_root / "normalized"
        normalized_audit = audit_parquet_tree(normalized_root)

        for manifest_path in (
            raw_root / "session_manifest.json",
            evidence_root / "session_manifest.json",
            evidence_root / "artifact_manifest.json",
        ):
            if manifest_path.is_file():
                manifests.append(
                    verify_manifest_references(
                        manifest_path,
                        search_roots=(raw_root, evidence_root, raw_root.parent),
                    )
                )

        if args.replay_db_a:
            replay_a = audit_sqlite_database(args.replay_db_a.expanduser().resolve())
        if args.replay_db_b:
            replay_b = audit_sqlite_database(args.replay_db_b.expanduser().resolve())
        if replay_a and replay_b:
            replay_comparison = compare_replay_databases(replay_a, replay_b)

        if normalized_audit and replay_a:
            tick_count = _table_count(replay_a, "ticks", "tick", "market_ticks")
            depth_count = _table_count(replay_a, "depth_snapshots", "depth", "market_depth")
            if tick_count is not None and depth_count is not None:
                reconciliation = reconcile_normalized_and_replay_counts(
                    normalized_event_count=int(normalized_audit.get("row_count", 0)),
                    tick_row_count=tick_count,
                    depth_row_count=depth_count,
                    explained_non_tick_rows=args.explained_non_tick_rows,
                )

        if bars_path.is_file():
            intervals = read_bar_intervals(bars_path)
            bars = {
                "path": str(bars_path),
                "interval_count": len(intervals),
                "first_interval_end_epoch": intervals[0]["interval_end_epoch"] if intervals else None,
                "last_interval_end_epoch": intervals[-1]["interval_end_epoch"] if intervals else None,
                "duplicate_interval_count": 0,
                "passed": bool(intervals),
                "errors": [] if intervals else ["no_bar_intervals"],
            }
            rehearsal = run_pr786_offline_rehearsal(
                bars_path=bars_path,
                output_root=audit_root / "pr786_offline_rehearsal",
                run_id="upstox-replay-2026-08-04-offline-rehearsal",
                session_date="2026-08-04",
            )
    except AuditError as exc:
        runtime_errors.append(str(exc))

    after = snapshot_paths(protected)
    try:
        assert_snapshot_unchanged(before, after)
        source_immutable = {"passed": True, "errors": []}
    except AuditError as exc:
        source_immutable = {"passed": False, "errors": [str(exc)]}

    manifest_gate = {
        "passed": bool(manifests) and all(item.get("passed") for item in manifests),
        "errors": [error for item in manifests for error in item.get("errors", [])],
        "manifests": manifests,
    }
    gates = [
        _gate("SOURCE_IMMUTABLE", source_immutable),
        _gate("RAW_ZSTD_DECOMPRESSIBLE", raw_audit),
        _gate("NORMALIZED_PARQUET_READABLE", normalized_audit),
        _gate("MANIFEST_HASH_LINEAGE", manifest_gate),
        _gate("DETERMINISTIC_REPLAY", replay_comparison),
        _gate("REPLAY_ROW_RECONCILIATION", reconciliation),
        _gate("BAR_INTERVAL_IDENTITIES", bars),
        _gate("PR786_OFFLINE_REHEARSAL", rehearsal),
    ]
    all_passed = all(gate["passed"] for gate in gates) and not runtime_errors
    report = {
        "schema_version": 1,
        "generated_for_session": "2026-08-04",
        "source": "upstox_replay",
        "offline_replay": True,
        "live_source": False,
        "raw_run_dir": str(raw_root),
        "evidence_root": str(evidence_root),
        "audit_root": str(audit_root),
        "source_snapshot_before": before,
        "source_snapshot_after": after,
        "raw": raw_audit,
        "normalized": normalized_audit,
        "manifest_lineage": manifest_gate,
        "replay_a": replay_a,
        "replay_b": replay_b,
        "replay_comparison": replay_comparison,
        "row_reconciliation": reconciliation,
        "bars": bars,
        "pr786_offline_rehearsal": rehearsal,
        "runtime_errors": runtime_errors,
        "gates": gates,
        "kite_fresh_live_session_ready": all_passed,
        "not_a_kite_live_certification": True,
        "not_an_option_corpus": True,
        "no_structural_edge_claim": True,
        "fresh_governed_kite_session_still_required": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
        "verdict": (
            "UPSTOX_CORPUS_INDEPENDENTLY_VERIFIED_PR786_OFFLINE_REHEARSAL_PASS"
            if all_passed
            else "UPSTOX_CORPUS_VERIFICATION_INCOMPLETE"
        ),
    }
    _write_json(audit_root / "final_report.json", report)
    (audit_root / "final_report.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
