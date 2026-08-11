"""Independent post-market certification for PR #763 and runtime authority.

The verifier is deliberately path-driven and read-only. It does not import or
invoke live runtime components, broker clients, feed handlers, strategy code,
or order routers. It accepts one completed evidence root plus one or more
operator-authority snapshot files and emits the strongest truthful verdict.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


PASS_VERDICT = "PASS_READ_ONLY_POST_MARKET_RELIABILITY"
PENDING_VERDICT = "IMPLEMENTATION_COMPLETE_LIVE_EVIDENCE_PENDING"
FAILED_VERDICT = "FAILED_CLOSED"

_DANGEROUS_TRUE_FLAGS = {
    "is_order_action",
    "order_action",
    "order_authority",
    "broker_write_authority",
    "allowed_for_live_execution",
    "allowed_for_paper_execution",
}
_CAPITAL_FIELDS = (
    "capital_assigned",
    "allocated_capital",
    "position_size_estimate",
    "capital_allocation",
)
_EXECUTION_FLAGS = (
    "execution_allowed",
    "eligible_for_execution",
    "truth_allows_execution",
    "tradable",
    "execution_ok",
    "selected_for_execution",
    "portfolio_optimization_selected",
)
_ID_FIELDS = ("trade_id", "candidate_id", "trade_key", "instrument_id", "id")


@dataclass(frozen=True)
class Gate:
    gate_id: str
    passed: bool
    evidence: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return float(default) if out != out else out


def _explicit_true(value: Any) -> bool:
    return value is True or (
        isinstance(value, int) and not isinstance(value, bool) and value == 1
    )


def _explicit_false(value: Any) -> bool:
    return value is False or (
        isinstance(value, int) and not isinstance(value, bool) and value == 0
    )


def _identity(row: Mapping[str, Any]) -> str:
    for field in _ID_FIELDS:
        text = str(row.get(field) or "").strip()
        if text:
            return text
    return ""


def _is_safe_relative(path_text: str) -> bool:
    path = Path(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def verify_sealed_evidence_root(root: str | Path) -> Gate:
    evidence_root = Path(root)
    errors: list[str] = []
    manifest_path = evidence_root / "artifact_manifest.json"
    sums_path = evidence_root / "SHA256SUMS"
    sealed_path = evidence_root / "SEALED"
    if not evidence_root.is_dir():
        errors.append("evidence_root_missing")
    for required in (manifest_path, sums_path, sealed_path):
        if not required.is_file():
            errors.append(f"missing:{required.name}")
    if errors:
        return Gate(
            "SEALED_EVIDENCE_ROOT",
            False,
            {"root": str(evidence_root), "errors": errors},
        )

    try:
        manifest = _safe_json(manifest_path)
        sealed = _safe_json(sealed_path)
    except Exception as exc:
        return Gate(
            "SEALED_EVIDENCE_ROOT",
            False,
            {
                "root": str(evidence_root),
                "errors": [f"metadata_parse_error:{type(exc).__name__}"],
            },
        )

    if not isinstance(manifest, Mapping) or not isinstance(
        manifest.get("artifacts"), list
    ):
        errors.append("manifest_invalid")
        artifacts: list[Any] = []
    else:
        artifacts = list(manifest.get("artifacts") or [])
    manifest_sha = sha256_file(manifest_path)
    if not isinstance(sealed, Mapping) or sealed.get("sealed") is not True:
        errors.append("sealed_marker_invalid")
    if str((sealed or {}).get("artifact_manifest_sha256") or "") != manifest_sha:
        errors.append("sealed_manifest_sha_mismatch")

    sums: dict[str, str] = {}
    for line_number, raw in enumerate(
        sums_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        text = raw.strip()
        if not text:
            continue
        parts = text.split(None, 1)
        if len(parts) != 2:
            errors.append(f"sha256sums_invalid_line:{line_number}")
            continue
        digest, relative = parts[0].strip(), parts[1].strip().lstrip("*")
        if relative in sums:
            errors.append(f"sha256sums_duplicate:{relative}")
        sums[relative] = digest

    declared: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            errors.append(f"artifact_invalid:{index}")
            continue
        relative = str(item.get("path") or "")
        if not _is_safe_relative(relative):
            errors.append(f"artifact_path_unsafe:{relative}")
            continue
        if relative in declared:
            errors.append(f"artifact_duplicate:{relative}")
            continue
        declared.add(relative)
        path = evidence_root / relative
        if not path.is_file():
            errors.append(f"artifact_missing:{relative}")
            continue
        expected_sha = str(item.get("sha256") or "")
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            errors.append(f"artifact_sha_mismatch:{relative}")
        try:
            expected_bytes = int(item.get("bytes"))
        except Exception:
            expected_bytes = -1
        if path.stat().st_size != expected_bytes:
            errors.append(f"artifact_size_mismatch:{relative}")
        if sums.get(relative) != expected_sha:
            errors.append(f"sha256sums_mismatch:{relative}")

    if set(sums) != declared:
        missing = sorted(declared - set(sums))
        extra = sorted(set(sums) - declared)
        if missing:
            errors.append(f"sha256sums_missing:{','.join(missing)}")
        if extra:
            errors.append(f"sha256sums_extra:{','.join(extra)}")

    actual_files = {
        str(path.relative_to(evidence_root))
        for path in evidence_root.rglob("*")
        if path.is_file()
        and path.name not in {"artifact_manifest.json", "SHA256SUMS", "SEALED"}
    }
    undeclared = sorted(actual_files - declared)
    missing_actual = sorted(declared - actual_files)
    if undeclared:
        errors.append(f"undeclared_artifacts:{','.join(undeclared)}")
    if missing_actual:
        errors.append(f"declared_artifacts_absent:{','.join(missing_actual)}")
    if int(manifest.get("artifact_count") or -1) != len(declared):
        errors.append("artifact_count_mismatch")

    return Gate(
        "SEALED_EVIDENCE_ROOT",
        not errors,
        {
            "root": str(evidence_root),
            "artifact_count": len(declared),
            "artifact_manifest_sha256": manifest_sha,
            "errors": errors,
        },
    )


def _iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as handle:
                for line_number, raw in enumerate(handle, start=1):
                    text = raw.strip()
                    if not text:
                        continue
                    try:
                        value = json.loads(text)
                    except Exception:
                        yield {
                            "_parse_error": line_number,
                            "_source_path": str(path),
                        }
                        continue
                    if isinstance(value, Mapping):
                        row = dict(value)
                        row.setdefault("_source_path", str(path))
                        yield row
        elif path.suffix.lower() == ".json":
            value = _safe_json(path)
            if isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("_source_path", str(path))
                yield row
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        row = dict(item)
                        row.setdefault("_source_path", str(path))
                        yield row
    except Exception:
        yield {"_parse_error": True, "_source_path": str(path)}


def _walk_mappings(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, Mapping):
        row = dict(value)
        yield row
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def _artifact_json_records(root: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in {".json", ".jsonl"}
            and path.name not in {"artifact_manifest.json", "SEALED"}
        ):
            for top in _iter_json_records(path):
                for row in _walk_mappings(top):
                    row.setdefault("_source_path", str(path))
                    yield row


def verify_read_only_evidence(root: str | Path) -> Gate:
    violations: list[str] = []
    parse_errors = 0
    records = 0
    for row in _artifact_json_records(Path(root)):
        records += 1
        if row.get("_parse_error"):
            parse_errors += 1
            continue
        source = str(row.get("_source_path") or "")
        for key in _DANGEROUS_TRUE_FLAGS:
            if key in row and _explicit_true(row.get(key)):
                violations.append(f"{key}=true:{source}")
        if "read_only" in row and _explicit_false(row.get("read_only")):
            violations.append(f"read_only=false:{source}")
        if "broker_api_called" in row and _explicit_true(
            row.get("broker_api_called")
        ):
            violations.append(f"broker_api_called=true:{source}")
    errors: list[str] = []
    if parse_errors:
        errors.append(f"json_parse_errors:{parse_errors}")
    errors.extend(sorted(set(violations)))
    return Gate(
        "READ_ONLY_NO_ORDER_AUTHORITY",
        not errors,
        {
            "records_scanned": records,
            "parse_errors": parse_errors,
            "violations": sorted(set(violations)),
            "errors": errors,
        },
    )


def _snapshot_payload(path: Path) -> Any:
    if path.suffix.lower() == ".jsonl":
        return list(_iter_json_records(path))
    return _safe_json(path)


def _collect_authority_rows(
    value: Any, *, container: str = ""
) -> Iterator[tuple[dict[str, Any], str]]:
    if isinstance(value, Mapping):
        row = dict(value)
        authority_keys = {
            "authority_state",
            "authority_allowed",
            "operator_bucket",
            "canonical_execution_decision",
        }
        if authority_keys.intersection(row):
            yield row, container
        for key, child in value.items():
            next_container = (
                str(key)
                if key
                in {
                    "top_executable",
                    "top_advisory",
                    "advisory",
                    "blocked_debug",
                    "rows",
                    "all_candidates",
                }
                else container
            )
            yield from _collect_authority_rows(child, container=next_container)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _collect_authority_rows(child, container=container)


def verify_authority_snapshots(snapshot_paths: Sequence[str | Path]) -> Gate:
    errors: list[str] = []
    rows: list[tuple[dict[str, Any], str, str]] = []
    snapshots = 0
    explicit_empty_snapshots = 0
    for raw_path in snapshot_paths:
        path = Path(raw_path)
        if not path.is_file():
            errors.append(f"snapshot_missing:{path}")
            continue
        snapshots += 1
        try:
            payload = _snapshot_payload(path)
        except Exception as exc:
            errors.append(
                f"snapshot_parse_error:{path}:{type(exc).__name__}"
            )
            continue
        found = list(_collect_authority_rows(payload))
        if not found and isinstance(payload, Mapping) and any(
            key in payload
            for key in (
                "top_executable",
                "top_advisory",
                "advisory",
                "blocked_debug",
            )
        ):
            explicit_empty_snapshots += 1
        rows.extend((row, container, str(path)) for row, container in found)

    executable_ids: set[str] = set()
    non_executable_ids: set[str] = set()
    executable_count = 0
    advisory_count = 0
    blocked_count = 0
    for index, (row, container, source) in enumerate(rows):
        state = str(row.get("authority_state") or "").strip().upper()
        allowed = _explicit_true(row.get("authority_allowed"))
        bucket = str(row.get("operator_bucket") or "").strip().upper()
        selection_score = _safe_float(row.get("selection_score"), default=-1.0)
        row_id = _identity(row) or f"row-{index}"
        fallback = any(
            _explicit_true(row.get(key))
            for key in (
                "fallback_used",
                "recovered_fallback",
                "synthetic",
                "is_synthetic",
                "stale_quote",
                "quote_is_stale",
            )
        )
        quote_source = str(
            row.get("quote_source") or row.get("option_ltp_source") or ""
        ).strip().upper()
        unsafe_quote_source = (not quote_source) or any(
            token in quote_source
            for token in ("FALLBACK", "SYNTHETIC", "UNKNOWN", "MOCK", "NONE")
        )
        if (
            state == "EXECUTABLE"
            or allowed
            or bucket == "TOP_EXECUTABLE"
            or container == "top_executable"
        ):
            executable_count += 1
            executable_ids.add(row_id)
            if state != "EXECUTABLE" or not allowed or bucket != "TOP_EXECUTABLE":
                errors.append(f"executable_truth_mismatch:{row_id}:{source}")
            if selection_score <= 0.0:
                errors.append(
                    f"executable_selection_score_not_positive:{row_id}:{source}"
                )
            if fallback or unsafe_quote_source:
                errors.append(f"unsafe_quote_in_executable:{row_id}:{source}")
            if any(
                field in row and _explicit_false(row.get(field))
                for field in _EXECUTION_FLAGS[:5]
            ):
                errors.append(f"executable_flag_false:{row_id}:{source}")
        else:
            non_executable_ids.add(row_id)
            if bucket == "ADVISORY_ONLY" or container in {
                "top_advisory",
                "advisory",
            }:
                advisory_count += 1
            else:
                blocked_count += 1
            if allowed or state == "EXECUTABLE":
                errors.append(f"non_executable_allowed:{row_id}:{source}")
            if abs(selection_score) > 1e-12:
                errors.append(
                    f"non_executable_selection_score_nonzero:{row_id}:{source}"
                )
            for field in _CAPITAL_FIELDS:
                if field in row and abs(_safe_float(row.get(field))) > 1e-12:
                    errors.append(
                        f"non_executable_capital_nonzero:{row_id}:{field}:{source}"
                    )
            for field in _EXECUTION_FLAGS:
                if field in row and _explicit_true(row.get(field)):
                    errors.append(
                        f"non_executable_flag_true:{row_id}:{field}:{source}"
                    )
    duplicates = sorted(executable_ids.intersection(non_executable_ids))
    if duplicates:
        errors.append(
            f"identity_in_executable_and_non_executable:{','.join(duplicates)}"
        )
    if snapshots == 0:
        errors.append("no_authority_snapshot")
    if snapshots > 0 and not rows and explicit_empty_snapshots == 0:
        errors.append("authority_fields_missing")

    return Gate(
        "RUNTIME_AUTHORITY_SNAPSHOTS",
        not errors,
        {
            "snapshot_count": snapshots,
            "explicit_empty_snapshot_count": explicit_empty_snapshots,
            "authority_row_count": len(rows),
            "executable_count": executable_count,
            "advisory_count": advisory_count,
            "blocked_count": blocked_count,
            "errors": errors,
        },
    )


def discover_live_semantics(root: str | Path) -> Gate:
    proof = {
        "post_mode_full_nifty_packets": False,
        "completed_constituent_bars": False,
        "market_event_graph_traversal": False,
        "shutdown_and_persistence_drain": False,
    }
    observations: dict[str, list[str]] = {key: [] for key in proof}
    for row in _artifact_json_records(Path(root)):
        source = str(row.get("_source_path") or "")
        if row.get("_parse_error"):
            continue
        proof_kind = str(
            row.get("proof_kind") or row.get("evidence_kind") or ""
        ).strip().upper()
        symbol = str(row.get("symbol") or row.get("underlying") or "").strip().upper()
        packet_mode = str(
            row.get("packet_mode") or row.get("mode") or row.get("kite_mode") or ""
        ).strip().upper()
        if (
            _safe_float(row.get("post_mode_full_packet_count")) > 0
            or _safe_float(row.get("nifty_post_mode_full_packet_count")) > 0
            or row.get("post_mode_full_receipt_epoch") not in (None, "", 0)
            or (
                symbol == "NIFTY"
                and packet_mode == "FULL"
                and _explicit_true(row.get("packet_received"))
            )
            or (
                proof_kind == "PR763_LIVE_ACCEPTANCE"
                and _explicit_true(row.get("post_mode_full_nifty_packets"))
            )
        ):
            proof["post_mode_full_nifty_packets"] = True
            observations["post_mode_full_nifty_packets"].append(source)
        completed_bars = row.get("completed_constituent_bars")
        if (
            isinstance(completed_bars, list)
            and len(completed_bars) > 0
            or _safe_float(row.get("completed_constituent_bar_count")) > 0
            or _safe_float(row.get("constituent_bar_count")) > 0
            or (
                proof_kind == "PR763_LIVE_ACCEPTANCE"
                and _safe_float(completed_bars) > 0
            )
        ):
            proof["completed_constituent_bars"] = True
            observations["completed_constituent_bars"].append(source)
        if (
            _safe_float(row.get("market_event_graph_traversal_count")) > 0
            or _safe_float(row.get("graph_traversal_count")) > 0
            or _safe_float(row.get("meg_traversal_count")) > 0
            or _explicit_true(row.get("meg_traversal_complete"))
            or _explicit_true(row.get("required_graph_traversal"))
            or (
                proof_kind == "PR763_LIVE_ACCEPTANCE"
                and _explicit_true(row.get("market_event_graph_traversal"))
            )
        ):
            proof["market_event_graph_traversal"] = True
            observations["market_event_graph_traversal"].append(source)
        if (
            _explicit_true(row.get("shutdown_drain_complete"))
            or _explicit_true(row.get("persistence_drain_complete"))
            or _explicit_true(row.get("shutdown_and_persistence_drain"))
            or (
                proof_kind == "PR763_LIVE_ACCEPTANCE"
                and _explicit_true(row.get("shutdown_and_persistence_drain"))
            )
        ):
            proof["shutdown_and_persistence_drain"] = True
            observations["shutdown_and_persistence_drain"].append(source)

    missing = sorted(key for key, value in proof.items() if not value)
    return Gate(
        "PR763_LIVE_SEMANTICS",
        not missing,
        {
            "proof": proof,
            "observations": {
                key: sorted(set(paths)) for key, paths in observations.items()
            },
            "missing": missing,
        },
    )


def _semantic_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def certify_pr763_session(
    *,
    evidence_root: str | Path,
    authority_snapshot_paths: Sequence[str | Path],
    output_dir: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    gates = [
        verify_sealed_evidence_root(evidence_root),
        verify_read_only_evidence(evidence_root),
        verify_authority_snapshots(authority_snapshot_paths),
        discover_live_semantics(evidence_root),
    ]
    foundational = all(gate.passed for gate in gates[:3])
    live_complete = gates[3].passed
    if not foundational:
        verdict = FAILED_VERDICT
    elif live_complete:
        verdict = PASS_VERDICT
    else:
        verdict = PENDING_VERDICT
    semantic = {
        "schema_version": 1,
        "verdict": verdict,
        "implementation_complete": foundational,
        "live_evidence_complete": live_complete,
        "read_only": True,
        "order_authority": False,
        "broker_write_authority": False,
        "gates": [asdict(gate) for gate in gates],
        "limitations": [
            "No strategy profitability or structural edge is certified.",
            "No broker connectivity, real fill quality, or production deployment is certified.",
            "Observed market contributors are not asserted as unique causes.",
        ],
    }
    report = {
        **semantic,
        "generated_at": generated_at
        or datetime.now(tz=timezone.utc).isoformat(),
        "semantic_sha256": _semantic_hash(semantic),
        "evidence_root": str(Path(evidence_root)),
        "authority_snapshot_paths": [
            str(Path(path)) for path in authority_snapshot_paths
        ],
    }
    if output_dir is not None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "pr763_post_market_reliability_certificate.json"
        md_path = target / "pr763_post_market_reliability_certificate.md"
        json_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report["json_path"] = str(json_path)
        report["markdown_path"] = str(md_path)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TradeBot PR #763 Post-Market Reliability Certificate",
        "",
        f"- Verdict: `{report.get('verdict')}`",
        f"- Implementation complete: `{report.get('implementation_complete')}`",
        f"- Live evidence complete: `{report.get('live_evidence_complete')}`",
        f"- Semantic SHA-256: `{report.get('semantic_sha256')}`",
        "",
        "## Gates",
        "",
    ]
    for gate in report.get("gates") or []:
        lines.append(
            f"- {'PASS' if gate.get('passed') else 'FAIL'} `{gate.get('gate_id')}`"
        )
        for error in gate.get("evidence", {}).get("errors", []) or []:
            lines.append(f"  - `{error}`")
        for missing in gate.get("evidence", {}).get("missing", []) or []:
            lines.append(f"  - missing: `{missing}`")
    lines.extend(["", "## Explicit exclusions", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


__all__ = [
    "FAILED_VERDICT",
    "PASS_VERDICT",
    "PENDING_VERDICT",
    "certify_pr763_session",
    "discover_live_semantics",
    "render_markdown",
    "verify_authority_snapshots",
    "verify_read_only_evidence",
    "verify_sealed_evidence_root",
]
