from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


REQUIRED_LATEST_FILES = (
    "feed_runtime_latest.json",
    "freshness_latest.json",
    "runtime_health_latest.json",
    "top_opportunities_latest.json",
    "option_chain_latest.json",
    "token_resolution_latest.json",
)

REQUIRED_LOG_TAILS = (
    "freshness_decisions_tail.jsonl",
    "rejected_candidates_tail.jsonl",
    "execution_entry_trace_tail.jsonl",
    "trade_lifecycle_tail.jsonl",
)

FALLBACK_SOURCES = {
    "fallback",
    "rest_fallback",
    "tick_store",
    "recovered_fallback",
    "synthetic_offhours",
    "subscription_failed",
    "quote_fallback",
    "close_fallback",
    "derived_fallback",
}


@dataclass(frozen=True)
class EvidenceReplayOptions:
    today: date | None = None
    quote_age_mismatch_tolerance_sec: float = 5.0
    max_jsonl_lines_per_file: int = 5000


@dataclass
class EvidenceSnapshotReport:
    name: str
    missing_latest_files: list[str] = field(default_factory=list)
    missing_log_tails: list[str] = field(default_factory=list)
    feed: dict[str, Any] = field(default_factory=dict)
    top_opportunities: dict[str, Any] = field(default_factory=dict)
    symbol_freshness: dict[str, dict[str, Any]] = field(default_factory=dict)
    expired_contracts: list[dict[str, Any]] = field(default_factory=list)
    quote_age_mismatches: list[dict[str, Any]] = field(default_factory=list)
    fallback_rows: list[dict[str, Any]] = field(default_factory=list)
    price_mismatch_rows: list[dict[str, Any]] = field(default_factory=list)
    candidate_status_counts: dict[str, int] = field(default_factory=dict)
    rejection_reason_counts: dict[str, int] = field(default_factory=dict)
    line_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class EvidenceReplayReport:
    source: str
    generated_at: str
    snapshot_count: int
    snapshots: list[EvidenceSnapshotReport]
    totals: dict[str, Any]
    evidence_map: dict[str, str]
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["broker_api_called"] = False
        payload["is_order_action"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_jsonl(path: Path, *, max_lines: int) -> Iterator[dict[str, Any]]:
    if not path.exists() or path.stat().st_size <= 0:
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return
    for line in lines[-max_lines:]:
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except Exception:
            continue
        if isinstance(value, dict):
            yield value


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return datetime.strptime(text.split("T", 1)[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _coerce_epoch_seconds(value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is not None:
        if numeric > 10_000_000_000:
            return float(numeric) / 1000.0
        return float(numeric)
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return float(parsed.timestamp())
    except Exception:
        return None


def _row_observation_epoch(row: dict[str, Any]) -> float | None:
    for field in (
        "decision_ts_epoch",
        "generated_at_epoch",
        "snapshot_ts_epoch",
        "display_ts_epoch",
        "event_ts_epoch",
        "timestamp_epoch",
        "ts_epoch",
        "created_at_epoch",
    ):
        epoch = _coerce_epoch_seconds(row.get(field))
        if epoch is not None:
            return epoch
    for field in (
        "decision_ts",
        "generated_at",
        "snapshot_ts",
        "timestamp",
        "ts_utc",
        "ts_ist",
        "created_at",
    ):
        epoch = _coerce_epoch_seconds(row.get(field))
        if epoch is not None:
            return epoch
    return None


def _infer_today(source: Path, options: EvidenceReplayOptions) -> date:
    if options.today is not None:
        return options.today
    text = str(source)
    for token in text.replace("-", "_").split("_"):
        if len(token) == 8 and token.isdigit():
            try:
                return datetime.strptime(token, "%Y%m%d").date()
            except Exception:
                pass
    return datetime.now().date()


_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def _safe_extract_tar(archive: tarfile.TarFile, root: Path) -> None:
    root_resolved = root.resolve()
    members = archive.getmembers()
    if len(members) > _MAX_ARCHIVE_MEMBERS:
        raise ValueError("evidence_archive_member_limit_exceeded")

    total_size = 0
    validated: list[tuple[tarfile.TarInfo, Path]] = []
    for member in members:
        if member.issym() or member.islnk():
            raise ValueError(f"evidence_archive_link_rejected:{member.name}")
        if not (member.isdir() or member.isfile()):
            raise ValueError(f"evidence_archive_special_member_rejected:{member.name}")
        if member.size < 0:
            raise ValueError(f"evidence_archive_negative_size:{member.name}")
        total_size += int(member.size)
        if total_size > _MAX_ARCHIVE_BYTES:
            raise ValueError("evidence_archive_size_limit_exceeded")
        target = (root_resolved / member.name).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"evidence_archive_path_traversal:{member.name}") from exc
        validated.append((member, target))

    for member, target in validated:
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(target, 0o700)
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"evidence_archive_member_unreadable:{member.name}")
        with source, target.open("xb") as handle:
            shutil.copyfileobj(source, handle)
        os.chmod(target, 0o600)


@contextmanager
def _evidence_root(source: str | Path) -> Iterator[Path]:
    path = Path(source)
    if path.is_dir():
        yield path
        return
    if path.is_file() and tarfile.is_tarfile(path):
        with tempfile.TemporaryDirectory(prefix="tradebot_evidence_") as tmp:
            root = Path(tmp)
            with tarfile.open(path, "r:*") as archive:
                _safe_extract_tar(archive, root)
            yield root
        return
    raise FileNotFoundError(f"evidence source not found or unsupported: {path}")


def _find_snapshots(root: Path) -> list[Path]:
    snapshots: list[Path] = []
    for latest_dir in root.rglob("runtime_latest"):
        snap = latest_dir.parent
        if (snap / "runtime_logs").exists() or (snap / "app_logs").exists():
            snapshots.append(snap)
    return sorted(set(snapshots), key=lambda p: str(p))


def _as_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for key, item in value.items():
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("symbol", key)
                rows.append(row)
            elif isinstance(item, list):
                for nested in item:
                    if isinstance(nested, dict):
                        row = dict(nested)
                        row.setdefault("symbol", key)
                        rows.append(row)
        return rows
    return []


def _flatten_rows(*values: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in values:
        rows.extend(_as_rows(value))
    return rows


def _record_symbol_freshness(snapshot: EvidenceSnapshotReport, freshness_payload: Any) -> None:
    for row in _flatten_rows(freshness_payload):
        symbol = _upper(row.get("symbol") or row.get("underlying") or row.get("name"))
        if not symbol:
            continue
        fresh = row.get("fresh")
        if fresh is None:
            fresh = row.get("quote_fresh") or row.get("fresh_quote_ok")
        age = _safe_float(row.get("quote_age_sec") or row.get("freshness_selected_age_sec") or row.get("age_sec"))
        reason = _text(row.get("freshness_reason") or row.get("reason") or row.get("reason_code"))
        snapshot.symbol_freshness[symbol] = {
            "fresh": bool(fresh) if fresh is not None else None,
            "age_sec": age,
            "reason": reason or None,
            "threshold_sec": _safe_float(row.get("threshold_sec") or row.get("freshness_threshold_sec")),
        }


def _iter_candidate_like_rows(snapshot_dir: Path, options: EvidenceReplayOptions) -> Iterator[dict[str, Any]]:
    runtime_logs = snapshot_dir / "runtime_logs"
    for name in REQUIRED_LOG_TAILS:
        path = runtime_logs / name
        for row in _iter_jsonl(path, max_lines=options.max_jsonl_lines_per_file):
            row = dict(row)
            row.setdefault("_source_file", name)
            yield row

    runtime_latest = snapshot_dir / "runtime_latest"
    for name in REQUIRED_LATEST_FILES:
        payload = _read_json(runtime_latest / name)
        for row in _flatten_rows(payload):
            row.setdefault("_source_file", name)
            yield row


def _detect_expired_contracts(snapshot: EvidenceSnapshotReport, rows: list[dict[str, Any]], *, today: date) -> None:
    for row in rows:
        expiry = _coerce_date(
            row.get("expiry")
            or row.get("expiry_date")
            or row.get("resolved_expiry")
            or row.get("requested_expiry")
        )
        if expiry is None or expiry >= today:
            continue
        snapshot.expired_contracts.append(
            {
                "source_file": row.get("_source_file"),
                "symbol": _upper(row.get("symbol") or row.get("underlying") or row.get("name")) or None,
                "tradingsymbol": row.get("tradingsymbol"),
                "instrument_token": row.get("instrument_token"),
                "expiry": expiry.isoformat(),
                "today": today.isoformat(),
            }
        )


def _detect_quote_age_mismatches(
    snapshot: EvidenceSnapshotReport,
    rows: list[dict[str, Any]],
    *,
    options: EvidenceReplayOptions,
) -> None:
    for row in rows:
        quote_ts_epoch = _safe_float(
            row.get("quote_ts_epoch")
            or row.get("option_ltp_timestamp")
            or row.get("ltp_ts_epoch")
            or row.get("quote_timestamp_epoch")
        )
        reported_age = _safe_float(
            row.get("quote_age_sec")
            or row.get("option_age_sec")
            or row.get("price_age_sec")
            or row.get("option_ltp_age_sec")
        )
        observation_epoch = _row_observation_epoch(row)
        if quote_ts_epoch is None or reported_age is None or observation_epoch is None:
            continue
        age_from_ts = max(0.0, float(observation_epoch) - float(quote_ts_epoch))
        delta = abs(float(age_from_ts) - float(reported_age))
        if delta <= float(options.quote_age_mismatch_tolerance_sec):
            continue
        snapshot.quote_age_mismatches.append(
            {
                "source_file": row.get("_source_file"),
                "symbol": _upper(row.get("symbol") or row.get("underlying")) or None,
                "trade_id": row.get("trade_id"),
                "quote_ts_epoch": quote_ts_epoch,
                "observation_epoch": observation_epoch,
                "reported_age_sec": reported_age,
                "age_from_timestamp_sec": round(age_from_ts, 6),
                "delta_sec": round(delta, 6),
                "quote_validation_status": row.get("quote_validation_status"),
            }
        )


def _detect_fallback_and_mismatch_rows(snapshot: EvidenceSnapshotReport, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sources = {
            _lower(row.get("quote_source")),
            _lower(row.get("option_ltp_source")),
            _lower(row.get("execution_entry_source")),
            _lower(row.get("display_entry_source")),
            _lower(row.get("entry_source")),
        }
        sources.discard("")
        fallback_hits = sorted(source for source in sources if source in FALLBACK_SOURCES)
        status = _upper(row.get("quote_validation_status") or row.get("validation_status"))
        if fallback_hits:
            snapshot.fallback_rows.append(
                {
                    "source_file": row.get("_source_file"),
                    "symbol": _upper(row.get("symbol") or row.get("underlying")) or None,
                    "trade_id": row.get("trade_id"),
                    "fallback_sources": fallback_hits,
                    "quote_validation_status": status or None,
                    "execution_allowed": row.get("execution_allowed"),
                    "candidate_status": row.get("candidate_status"),
                }
            )
        if status == "PRICE_MISMATCH" or _safe_float(row.get("quote_consistency_score")) == 0.0:
            snapshot.price_mismatch_rows.append(
                {
                    "source_file": row.get("_source_file"),
                    "symbol": _upper(row.get("symbol") or row.get("underlying")) or None,
                    "trade_id": row.get("trade_id"),
                    "quote_validation_status": status or None,
                    "quote_consistency_score": row.get("quote_consistency_score"),
                    "current_ltp": row.get("current_ltp"),
                    "best_bid": row.get("best_bid") or row.get("bid"),
                    "best_ask": row.get("best_ask") or row.get("ask"),
                }
            )


def _record_candidate_counts(snapshot: EvidenceSnapshotReport, rows: list[dict[str, Any]]) -> None:
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for row in rows:
        status = _lower(
            row.get("candidate_status")
            or row.get("execution_status")
            or row.get("readiness")
            or row.get("permission")
        )
        if status:
            statuses[status] += 1
        reason = _lower(
            row.get("reject_reason")
            or row.get("entry_block_code")
            or row.get("reason_code")
            or row.get("reason")
            or row.get("permission_reason")
        )
        if reason:
            reasons[reason] += 1
    snapshot.candidate_status_counts = dict(statuses)
    snapshot.rejection_reason_counts = dict(reasons)


def _extract_feed_summary(feed_payload: Any) -> dict[str, Any]:
    if not isinstance(feed_payload, dict):
        return {}
    return {
        "feed_ok": feed_payload.get("feed_ok"),
        "effective_ws_connected": feed_payload.get("effective_ws_connected"),
        "last_error": feed_payload.get("last_error"),
        "state": feed_payload.get("state") or feed_payload.get("feed_state"),
        "last_tick_age_sec": feed_payload.get("last_tick_age_sec"),
        "option_last_tick_age_by_symbol": feed_payload.get("option_last_tick_age_by_symbol"),
        "option_feed_block_reason_by_symbol": feed_payload.get("option_feed_block_reason_by_symbol"),
    }


def _extract_top_opportunity_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    fields = (
        "top_executable_count",
        "top_advisory_count",
        "source_candidate_count",
        "phase2_ranked_count",
        "phase2_reason",
        "selector_outcome",
        "selected_count",
    )
    out = {field: payload.get(field) for field in fields if field in payload}
    for key in ("top_executable", "top_advisory", "ranked_candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            out[f"{key}_len"] = len(value)
    return out


def _analyze_snapshot(snapshot_dir: Path, *, source_root: Path, today: date, options: EvidenceReplayOptions) -> EvidenceSnapshotReport:
    try:
        name = str(snapshot_dir.relative_to(source_root))
    except Exception:
        name = snapshot_dir.name
    report = EvidenceSnapshotReport(name=name)
    runtime_latest = snapshot_dir / "runtime_latest"
    runtime_logs = snapshot_dir / "runtime_logs"

    for name_latest in REQUIRED_LATEST_FILES:
        if not (runtime_latest / name_latest).exists():
            report.missing_latest_files.append(name_latest)
    for name_log in REQUIRED_LOG_TAILS:
        path = runtime_logs / name_log
        if not path.exists():
            report.missing_log_tails.append(name_log)
        else:
            report.line_counts[name_log] = sum(1 for _ in _iter_jsonl(path, max_lines=options.max_jsonl_lines_per_file))

    feed_payload = _read_json(runtime_latest / "feed_runtime_latest.json")
    freshness_payload = _read_json(runtime_latest / "freshness_latest.json")
    top_payload = _read_json(runtime_latest / "top_opportunities_latest.json")
    option_chain_payload = _read_json(runtime_latest / "option_chain_latest.json")
    token_payload = _read_json(runtime_latest / "token_resolution_latest.json")

    report.feed = _extract_feed_summary(feed_payload)
    report.top_opportunities = _extract_top_opportunity_summary(top_payload)
    _record_symbol_freshness(report, freshness_payload)

    rows = list(_iter_candidate_like_rows(snapshot_dir, options))
    rows.extend(_flatten_rows(option_chain_payload, token_payload, top_payload, freshness_payload, feed_payload))

    _detect_expired_contracts(report, rows, today=today)
    _detect_quote_age_mismatches(report, rows, options=options)
    _detect_fallback_and_mismatch_rows(report, rows)
    _record_candidate_counts(report, rows)

    if report.feed.get("feed_ok") is False:
        report.warnings.append("feed_not_ok")
    if report.top_opportunities.get("top_executable_count") == 0:
        report.warnings.append("zero_top_executable")
    if report.expired_contracts:
        report.warnings.append("expired_contract_detected")
    if report.quote_age_mismatches:
        report.warnings.append("quote_age_mismatch_detected")
    if report.fallback_rows:
        report.warnings.append("fallback_rows_detected")
    if report.price_mismatch_rows:
        report.warnings.append("price_mismatch_rows_detected")
    return report


def _totals(snapshots: list[EvidenceSnapshotReport]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    symbols_with_stale: set[str] = set()
    feed_not_ok = 0
    zero_executable_snapshots = 0
    line_counts: Counter[str] = Counter()

    for snapshot in snapshots:
        status_counts.update(snapshot.candidate_status_counts)
        reason_counts.update(snapshot.rejection_reason_counts)
        line_counts.update(snapshot.line_counts)
        if snapshot.feed.get("feed_ok") is False:
            feed_not_ok += 1
        if snapshot.top_opportunities.get("top_executable_count") == 0:
            zero_executable_snapshots += 1
        for symbol, freshness in snapshot.symbol_freshness.items():
            if freshness.get("fresh") is False:
                symbols_with_stale.add(symbol)

    return {
        "snapshots": len(snapshots),
        "feed_not_ok_snapshots": feed_not_ok,
        "zero_executable_snapshots": zero_executable_snapshots,
        "expired_contract_count": sum(len(s.expired_contracts) for s in snapshots),
        "quote_age_mismatch_count": sum(len(s.quote_age_mismatches) for s in snapshots),
        "fallback_row_count": sum(len(s.fallback_rows) for s in snapshots),
        "price_mismatch_row_count": sum(len(s.price_mismatch_rows) for s in snapshots),
        "symbols_with_stale_freshness": sorted(symbols_with_stale),
        "candidate_status_counts": dict(status_counts),
        "top_rejection_reasons": dict(reason_counts.most_common(12)),
        "line_counts": dict(line_counts),
    }


def _evidence_map(totals: dict[str, Any]) -> dict[str, str]:
    return {
        "feed_split_or_unhealthy": "evidence_present" if totals.get("feed_not_ok_snapshots") else "not_observed",
        "expired_contracts": "evidence_present" if totals.get("expired_contract_count") else "not_observed",
        "quote_age_mismatch": "evidence_present" if totals.get("quote_age_mismatch_count") else "not_observed",
        "fallback_or_rest_rows": "evidence_present" if totals.get("fallback_row_count") else "not_observed",
        "price_mismatch_rows": "evidence_present" if totals.get("price_mismatch_row_count") else "not_observed",
        "zero_executable_opportunities": "evidence_present" if totals.get("zero_executable_snapshots") else "not_observed",
        "stale_symbol_freshness": "evidence_present" if totals.get("symbols_with_stale_freshness") else "not_observed",
    }


def _verdict(totals: dict[str, Any]) -> str:
    hard_failures = [
        totals.get("expired_contract_count", 0),
        totals.get("quote_age_mismatch_count", 0),
        totals.get("fallback_row_count", 0),
        totals.get("price_mismatch_row_count", 0),
    ]
    if any(int(v or 0) > 0 for v in hard_failures):
        return "NOT_READY_EXECUTION_TRUTH_FAILED"
    if totals.get("feed_not_ok_snapshots"):
        return "NOT_READY_FEED_UNHEALTHY"
    if totals.get("zero_executable_snapshots"):
        return "NO_EXECUTABLE_OPPORTUNITIES_OBSERVED"
    return "EVIDENCE_REPLAY_OK"


def generate_evidence_replay_report(
    source: str | Path,
    *,
    options: EvidenceReplayOptions | None = None,
) -> EvidenceReplayReport:
    options = options or EvidenceReplayOptions()
    source_path = Path(source)
    today = _infer_today(source_path, options)
    with _evidence_root(source_path) as root:
        snapshots = [
            _analyze_snapshot(snapshot, source_root=root, today=today, options=options)
            for snapshot in _find_snapshots(root)
        ]
    totals = _totals(snapshots)
    evidence_map = _evidence_map(totals)
    return EvidenceReplayReport(
        source=str(source_path),
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        snapshot_count=len(snapshots),
        snapshots=snapshots,
        totals=totals,
        evidence_map=evidence_map,
        verdict=_verdict(totals),
    )


def report_to_markdown(report: EvidenceReplayReport) -> str:
    data = report.to_dict()
    totals = data["totals"]
    lines = [
        "# EDGE-37 Evidence Replay Quality Report",
        "",
        f"source: `{data['source']}`",
        f"generated_at: `{data['generated_at']}`",
        f"verdict: `{data['verdict']}`",
        f"snapshot_count: `{data['snapshot_count']}`",
        "",
        "## Totals",
        "",
    ]
    for key in (
        "feed_not_ok_snapshots",
        "zero_executable_snapshots",
        "expired_contract_count",
        "quote_age_mismatch_count",
        "fallback_row_count",
        "price_mismatch_row_count",
        "symbols_with_stale_freshness",
        "candidate_status_counts",
        "top_rejection_reasons",
    ):
        lines.append(f"- {key}: `{json.dumps(totals.get(key), sort_keys=True)}`")
    lines.extend(["", "## Evidence Map", ""])
    for key, value in data["evidence_map"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Snapshot Warnings", ""])
    for snapshot in data["snapshots"]:
        warnings = snapshot.get("warnings") or []
        if warnings:
            lines.append(f"- {snapshot['name']}: `{', '.join(warnings)}`")
    if not any(snapshot.get("warnings") for snapshot in data["snapshots"]):
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)
