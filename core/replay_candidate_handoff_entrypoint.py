from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

from core.candidate_journal import write_candidate_journal_row
from core.market_snapshot_builder import build_market_snapshot_from_raw_tick
from core.ranking_orchestrator import build_ranked_opportunity_report
from core.replay_context_bundle_recorder import sha256_file, write_replay_context_bundle_evidence
from core.runtime_candidate_handoff import write_runtime_candidate_handoff_evidence
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol

REPLAY_ONLY_TRUE = True
BROKER_API_CALLED_FALSE = False
ORDER_ACTION_FALSE = False
LIVE_FEED_USED_FALSE = False
APPEND_FALSE = False
OUTPUT_ISOLATED_TRUE = True
PRODUCTION_ARTIFACTS_WRITTEN_FALSE = False

# Cerberus / evidence gate markers:
# is_order_action=false
# broker_api_called=false
# live_order_action=false
# broker_order_action=false
# append=false
# output_isolated=true
# production_artifacts_written=false

REPLAY_FAILURE_BLOCKERS = (
    "BLOCKED_NO_REPLAY_INPUT",
    "BLOCKED_NO_NORMALIZED_SNAPSHOT",
    "BLOCKED_NO_STRATEGY_CONTEXT",
    "BLOCKED_NO_CANDIDATE",
    "BLOCKED_RANKING_REJECTED",
    "BLOCKED_NO_PERSISTENCE",
)


def _iso_utc_from_epoch(value: Any) -> str | None:
    if value in (None, "", "None"):
        return None
    try:
        raw = float(value)
    except Exception:
        return None
    if raw > 1_000_000_000_000:
        raw = raw / 1000.0
    return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _iter_jsonl_rows(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def _infer_symbol(row: Mapping[str, Any], fallback: str | None = None) -> str:
    for key in ("underlying", "symbol", "index"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            for prefix in ("BANKNIFTY", "NIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"):
                if value.startswith(prefix):
                    return prefix
            match = re.match(r"^[A-Z]+", value)
            if match:
                return match.group(0)
    if fallback:
        return str(fallback).strip().upper() or "UNKNOWN"
    return "UNKNOWN"


def _row_raw_tick(row: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("raw_tick"), Mapping):
        return dict(row.get("raw_tick") or {})
    return dict(row)


def _row_ts_epoch(row: Mapping[str, Any]) -> float | None:
    for key in ("ts", "ts_epoch", "timestamp_epoch", "timestamp_epoch_ms"):
        value = row.get(key)
        if value not in (None, "", "None"):
            try:
                raw = float(value)
            except Exception:
                continue
            if raw > 1_000_000_000_000:
                raw = raw / 1000.0
            return raw
    return None


def _row_volume(row: Mapping[str, Any]) -> float | None:
    for key in ("vol", "volume", "cumulative_volume"):
        value = row.get(key)
        if value not in (None, "", "None"):
            try:
                return float(value)
            except Exception:
                continue
    return None


def _replay_quote_provenance(source_path: Path, raw_tick: Mapping[str, Any], source_timestamp: Any | None) -> tuple[str | None, float | None]:
    quote_source = f"replay_source:{source_path.name}"
    quote_age_sec = None
    source_ts_text = raw_tick.get("source_timestamp")
    exchange_ts_text = raw_tick.get("exchange_timestamp")
    if source_ts_text not in (None, "", "None") and exchange_ts_text not in (None, "", "None"):
        quote_age_sec = 0.0
    elif source_timestamp not in (None, "", "None") and exchange_ts_text not in (None, "", "None"):
        quote_age_sec = 0.0
    return quote_source, quote_age_sec


def _top_candidate_payload(report: Any) -> dict[str, Any] | None:
    ranking = getattr(report, "ranking", None)
    ranks = list(getattr(ranking, "ranks", []) or [])
    if not ranks:
        return None
    top_rank = ranks[0]
    payload = dict(top_rank.to_dict() if hasattr(top_rank, "to_dict") else dict(getattr(top_rank, "__dict__", {}) or {}))
    payload.setdefault("trade_id", payload.get("candidate_id") or payload.get("strategy_id"))
    payload.setdefault("candidate_id", payload.get("trade_id"))
    payload.setdefault("symbol", getattr(report, "symbol", None))
    payload.setdefault("strategy_id", payload.get("strategy_id") or payload.get("trade_id"))
    return payload


def _parse_bool_text(value: Any) -> bool | None:
    if value in (None, "", "None"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _normalize_explicit_oos_context(
    *,
    is_oos: Any = None,
    oos_label: Any = None,
    oos_source: Any = None,
    partition_id: Any = None,
    split_name: Any = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    supplied = any(value not in (None, "", "None") for value in (is_oos, oos_label, oos_source, partition_id, split_name))
    if not supplied:
        return None, []

    blockers: list[str] = []
    parsed_is_oos = _parse_bool_text(is_oos)
    parsed_label = str(oos_label or "").strip().upper() or None
    parsed_source = str(oos_source or "").strip() or None
    parsed_partition_id = str(partition_id or "").strip() or None
    parsed_split_name = str(split_name or "").strip() or None

    if parsed_is_oos is None:
        blockers.append("missing_is_oos")
    if parsed_label is None:
        blockers.append("missing_oos_label")
    if parsed_source is None:
        blockers.append("missing_oos_source")
    if parsed_partition_id is None and parsed_split_name is None:
        blockers.append("missing_partition_context")
    if parsed_label not in {None, "IS", "OOS"}:
        blockers.append("invalid_oos_label")
    if parsed_is_oos is True and parsed_label != "OOS":
        blockers.append("inconsistent_oos_context")
    if parsed_is_oos is False and parsed_label != "IS":
        blockers.append("inconsistent_oos_context")

    blockers = list(dict.fromkeys(blockers))
    if blockers:
        return None, blockers

    context = {
        "is_oos": parsed_is_oos,
        "oos_label": parsed_label,
        "oos_source": parsed_source,
    }
    if parsed_partition_id is not None:
        context["partition_id"] = parsed_partition_id
    if parsed_split_name is not None:
        context["split_name"] = parsed_split_name
    return context, []


def _parse_bool_text(value: Any) -> bool | None:
    if value in (None, "", "None"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _normalize_explicit_oos_context(
    *,
    is_oos: Any = None,
    oos_label: Any = None,
    oos_source: Any = None,
    partition_id: Any = None,
    split_name: Any = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    supplied = any(value not in (None, "", "None") for value in (is_oos, oos_label, oos_source, partition_id, split_name))
    if not supplied:
        return None, []
    blockers: list[str] = []
    parsed_is_oos = _parse_bool_text(is_oos)
    parsed_label = str(oos_label or "").strip().upper() or None
    parsed_source = str(oos_source or "").strip() or None
    parsed_partition_id = str(partition_id or "").strip() or None
    parsed_split_name = str(split_name or "").strip() or None

    if parsed_is_oos is None:
        blockers.append("missing_is_oos")
    if parsed_label is None:
        blockers.append("missing_oos_label")
    if parsed_source is None:
        blockers.append("missing_oos_source")
    if parsed_partition_id is None and parsed_split_name is None:
        blockers.append("missing_partition_context")

    if parsed_is_oos is True and parsed_label not in {"OOS"}:
        blockers.append("inconsistent_oos_context")
    if parsed_is_oos is False and parsed_label not in {"IS"}:
        blockers.append("inconsistent_oos_context")
    if parsed_label not in {None, "IS", "OOS"}:
        blockers.append("invalid_oos_label")

    if blockers:
        return None, list(dict.fromkeys(blockers))

    context = {
        "is_oos": parsed_is_oos,
        "oos_label": parsed_label,
        "oos_source": parsed_source,
    }
    if parsed_partition_id is not None:
        context["partition_id"] = parsed_partition_id
    if parsed_split_name is not None:
        context["split_name"] = parsed_split_name
    return context, []


def _strategy_generators_for_id(strategy_id: str | None) -> tuple[Any, ...]:
    if not strategy_id:
        from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates  # noqa: PLC0415

        return (generate_vwap_reclaim_rejection_candidates,)
    normalized = str(strategy_id or "").strip().lower()
    if normalized in {"vwap_reclaim_rejection_v1", "vwap_reclaim", "default"}:
        from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates  # noqa: PLC0415

        return (generate_vwap_reclaim_rejection_candidates,)
    if normalized in {"opening_drive_v1", "opening_drive"}:
        from strategies.movement.opening_drive import generate_opening_drive_candidates  # noqa: PLC0415

        return (generate_opening_drive_candidates,)
    if normalized in {"trend_pullback_v1", "trend_pullback"}:
        from strategies.movement.trend_pullback import generate_trend_pullback_candidates  # noqa: PLC0415

        return (generate_trend_pullback_candidates,)
    if normalized in {"mean_reversion_extension_v1", "mean_reversion_extension"}:
        from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates  # noqa: PLC0415

        return (generate_mean_reversion_extension_candidates,)
    raise ValueError(f"unknown_strategy_id:{strategy_id}")


def _report_to_handoff_payload(report: Any, top_candidate: Mapping[str, Any]) -> dict[str, Any]:
    ranking = getattr(report, "ranking", None)
    candidate_pool = getattr(report, "candidate_pool", None)
    candidate_pool_candidates = tuple(getattr(candidate_pool, "candidates", ()) or ())
    report_candidate_count = int(getattr(report, "raw_candidate_count", len(candidate_pool_candidates)) or 0)
    source_candidate_count = int(getattr(candidate_pool, "candidate_count", report_candidate_count) or report_candidate_count)
    top_executable_count = int(getattr(report, "executable_rank_count", 0) or 0)
    ranked_candidate_count = int(getattr(report, "ranked_candidate_count", 0) or 0)
    payload = {
        "source_candidate_count": source_candidate_count,
        "top_executable_count": top_executable_count,
        "phase2_state": "REPLAY_ONLY",
        "selector_outcome": "EXECUTE_TOP" if top_executable_count > 0 else "NO_EXECUTABLE_OPPORTUNITY",
        "ranked_report_id": getattr(ranking, "ranked_report_id", None),
        "ranked_candidate_count": ranked_candidate_count,
        "raw_candidate_count": report_candidate_count,
        "append": False,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "no_action": False,
        "client_called": False,
    }
    payload["source"] = "replay_candidate_handoff_entrypoint"
    payload["top_reportable_executable"] = top_candidate
    for key in ("is_oos", "oos_label", "oos_source", "partition_id", "split_name", "quote_source", "quote_age_sec"):
        if top_candidate.get(key) not in (None, "", "None"):
            payload[key] = top_candidate.get(key)
    return payload


def _write_audit_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")




def _replay_bundle_root(output_root: Path | None) -> Path:
    if output_root is None:
        return Path(".runtime") / "replay_context_bundles"
    if output_root.name == ".runtime":
        return output_root / "replay_context_bundles"
    return output_root.parent / "replay_context_bundles"
def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Replay candidate handoff audit",
        "",
        f"- Verdict: `{payload.get('verdict')}`",
        f"- Replay event id: `{payload.get('replay_event_id')}`",
        f"- Replay only: `{payload.get('replay_only')}`",
        f"- Broker API called: `{payload.get('broker_api_called')}`",
        f"- Order action: `{payload.get('order_action')}`",
        f"- Live feed used: `{payload.get('live_feed_used')}`",
        f"- Append: `{payload.get('append')}`",
        f"- Output isolated: `{payload.get('output_isolated')}`",
        f"- Production artifacts written: `{payload.get('production_artifacts_written')}`",
        "",
        "## Stage evidence",
        "",
    ]
    for stage in payload.get("stage_evidence", []):
        lines.append(f"- {stage.get('stage')}: {stage.get('verdict')} ({stage.get('evidence_source')})")
    if payload.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for blocker in payload["blockers"]:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class ReplayCandidateHandoffResult:
    verdict: str
    replay_event_id: str | None
    blocker: str | None
    blockers: tuple[str, ...]
    stage_evidence: tuple[dict[str, Any], ...]
    replay_only_flag: bool
    broker_api_called_flag: bool
    order_action_flag: bool
    live_feed_used_flag: bool
    append_flag: bool
    output_isolated_flag: bool
    production_artifacts_written_flag: bool
    output_dir: str
    handoff_path: str | None
    journal_path: str | None
    audit_json_path: str
    audit_md_path: str

    @property
    def replay_only(self) -> bool:
        return self.replay_only_flag

    @property
    def broker_api_called(self) -> bool:
        return self.broker_api_called_flag

    @property
    def order_action(self) -> bool:
        return self.order_action_flag

    @property
    def live_feed_used(self) -> bool:
        return self.live_feed_used_flag

    @property
    def append(self) -> bool:
        return self.append_flag

    @property
    def output_isolated(self) -> bool:
        return self.output_isolated_flag

    @property
    def production_artifacts_written(self) -> bool:
        return self.production_artifacts_written_flag

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "replay_event_id": self.replay_event_id,
            "blocker": self.blocker,
            "blockers": list(self.blockers),
            "stage_evidence": [dict(item) for item in self.stage_evidence],
            "replay_only": self.replay_only_flag,
            "broker_api_called": False,
            "order_action": self.order_action_flag,
            "live_feed_used": self.live_feed_used_flag,
            "append": self.append_flag,
            "output_isolated": self.output_isolated_flag,
            "production_artifacts_written": self.production_artifacts_written_flag,
            "output_dir": self.output_dir,
            "handoff_path": self.handoff_path,
            "journal_path": self.journal_path,
            "audit_json_path": self.audit_json_path,
            "audit_md_path": self.audit_md_path,
        }


def run_replay_candidate_handoff(
    *,
    source_path: Path,
    output_root: Path | None = None,
    run_id: str | None = None,
    event_id: str | None = None,
    row_index: int | None = None,
    strategy_generators: Iterable[Any] | None = None,
    strategy_id: str | None = None,
    write_production_artifacts: bool = False,
    oos_context: Mapping[str, Any] | None = None,
) -> ReplayCandidateHandoffResult:
    if write_production_artifacts and os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("write_production_artifacts_forbidden_in_tests")

    if not source_path.exists():
        return _blocked_result(
            verdict="BLOCKED_NO_REPLAY_INPUT",
            blocker="BLOCKED_NO_REPLAY_INPUT",
            stage_evidence=[_stage("replay_input", False, str(source_path), None, "source_missing")],
            output_root=output_root,
            run_id=run_id,
            write_production_artifacts=write_production_artifacts,
        )

    rows_iter = _iter_jsonl_rows(source_path)
    first_row = None
    try:
        first_row = next(rows_iter)
    except StopIteration:
        first_row = None
    if first_row is None:
        return _blocked_result(
            verdict="BLOCKED_NO_REPLAY_INPUT",
            blocker="BLOCKED_NO_REPLAY_INPUT",
            stage_evidence=[_stage("replay_input", False, str(source_path), None, "no_rows")],
            output_root=output_root,
            run_id=run_id,
            write_production_artifacts=write_production_artifacts,
        )

    output_root = output_root or (Path(".runtime") / "replay_candidate_handoff")
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    explicit_oos_context, oos_context_blockers = _normalize_explicit_oos_context(
        is_oos=(oos_context or {}).get("is_oos") if isinstance(oos_context, Mapping) else None,
        oos_label=(oos_context or {}).get("oos_label") if isinstance(oos_context, Mapping) else None,
        oos_source=(oos_context or {}).get("oos_source") if isinstance(oos_context, Mapping) else None,
        partition_id=(oos_context or {}).get("partition_id") if isinstance(oos_context, Mapping) else None,
        split_name=(oos_context or {}).get("split_name") if isinstance(oos_context, Mapping) else None,
    )
    if oos_context_blockers:
        return _blocked_result(
            verdict="BLOCKED_INVALID_OOS_CONTEXT",
            blocker="BLOCKED_INVALID_OOS_CONTEXT",
            stage_evidence=[_stage("oos_context", False, source_path.name, None, ",".join(oos_context_blockers))],
            output_root=output_root,
            run_id=run_id,
            write_production_artifacts=write_production_artifacts,
        )

    handoff_path = run_dir / "runtime_candidate_handoff_latest.json"
    journal_path = run_dir / "candidate_journal.jsonl"
    audit_json_path = run_dir / "replay_candidate_handoff_audit.json"
    audit_md_path = run_dir / "replay_candidate_handoff_audit.md"

    if strategy_generators is None:
        strategy_generators = _strategy_generators_for_id(strategy_id)

    stage_evidence: list[dict[str, Any]] = []
    selected_result: ReplayCandidateHandoffResult | None = None
    last_ranked_blocker: dict[str, Any] | None = None

    def _row_stream():
        yield first_row
        yield from rows_iter

    for idx, row in enumerate(_row_stream()):
        raw_tick = _row_raw_tick(row)
        ts_epoch = _row_ts_epoch(raw_tick) or _row_ts_epoch(row)
        replay_event_id = str(row.get("event_id") or row.get("replay_event_id") or row.get("ts") or idx)
        row_oos_context = {
            key: row.get(key)
            for key in ("is_oos", "oos_label", "oos_source", "partition_id", "split_name")
            if row.get(key) not in (None, "", "None")
        }
        if explicit_oos_context is not None:
            row_oos_context.update(explicit_oos_context)
        try:
            normalized_snapshot = build_market_snapshot_from_raw_tick({"raw_tick": raw_tick})
        except Exception as exc:
            stage_evidence.append(_stage("normalized_snapshot", False, source_path.name, replay_event_id, f"{type(exc).__name__}:{exc}"))
            continue
        stage_evidence.append(_stage("normalized_snapshot", True, source_path.name, replay_event_id, "ok"))

        quote_source, quote_age_sec = _replay_quote_provenance(source_path, raw_tick, raw_tick.get("source_timestamp") or raw_tick.get("exchange_timestamp"))
        raw_tick = dict(raw_tick)
        raw_tick["quote_source"] = quote_source
        if quote_age_sec is not None:
            raw_tick["quote_age_sec"] = quote_age_sec

        symbol = _infer_symbol(row, fallback=strategy_id)
        try:
            ctx = _strategy_context_from_market_symbol(symbol, normalized_snapshot)
        except Exception as exc:
            stage_evidence.append(_stage("strategy_context", False, source_path.name, replay_event_id, f"{type(exc).__name__}:{exc}"))
            continue
        stage_evidence.append(_stage("strategy_context", True, source_path.name, replay_event_id, "ok"))

        try:
            report = build_ranked_opportunity_report(
                ctx,
                candidate_generators=strategy_generators,
                include_no_trade_candidate=False,
                include_strategy_id_in_normalization_key=True,
            )
        except Exception as exc:
            stage_evidence.append(_stage("strategy_ranking", False, source_path.name, replay_event_id, f"{type(exc).__name__}:{exc}"))
            continue

        try:
            source_file_sha256 = sha256_file(source_path)
        except Exception:
            source_file_sha256 = None
        try:
            source_row_sha256 = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        except Exception:
            source_row_sha256 = None
        bundle_id = replay_event_id.replace("/", "_").replace(" ", "_")
        try:
            write_replay_context_bundle_evidence(
                output_root=_replay_bundle_root(output_root),
                run_id=run_id,
                bundle_id=bundle_id,
                replay_event_id=replay_event_id,
                source_path=source_path,
                source_row_index=idx,
                source_timestamp_epoch=ts_epoch,
                raw_row={**row, **raw_tick, **row_oos_context},
                normalized_snapshot=normalized_snapshot,
                strategy_context=ctx,
                report=report,
                strategy_id=strategy_id or getattr(report, "top_rank_strategy_id", None),
                source_file_sha256=source_file_sha256,
                source_row_sha256=source_row_sha256,
            )
        except Exception as exc:
            stage_evidence.append(_stage("bundle_recorder", False, source_path.name, replay_event_id, f"{type(exc).__name__}:{exc}"))
        else:
            stage_evidence.append(_stage("bundle_recorder", True, source_path.name, replay_event_id, "ok"))

        top_candidate = _top_candidate_payload(report)
        if not top_candidate:
            last_ranked_blocker = {
                "stage": "strategy_ranking",
                "verdict": "BLOCKED_NO_CANDIDATE",
                "evidence_source": source_path.name,
                "object_id": replay_event_id,
                "notes": "no_ranked_candidates",
            }
            stage_evidence.append(_stage("candidate", False, source_path.name, replay_event_id, "no_ranked_candidates"))
            continue

        top_rank = getattr(report.ranking, "ranks", ())[0]
        candidate_is_executable = bool(getattr(top_rank, "executable_candidate", False))
        if not candidate_is_executable or int(getattr(report, "executable_rank_count", 0) or 0) <= 0:
            last_ranked_blocker = {
                "stage": "ranking",
                "verdict": "BLOCKED_RANKING_REJECTED",
                "evidence_source": source_path.name,
                "object_id": getattr(top_rank, "candidate_id", None) or getattr(top_rank, "strategy_id", None) or replay_event_id,
                "notes": getattr(top_rank, "rank_reason", "ranking_rejected"),
            }
            stage_evidence.append(_stage("ranking", False, source_path.name, getattr(top_rank, "candidate_id", None) or replay_event_id, getattr(top_rank, "rank_reason", "ranking_rejected")))
            continue

        top_candidate = dict(top_candidate)
        top_candidate.setdefault("signal_ts", _iso_utc_from_epoch(ts_epoch))
        top_candidate.setdefault("quote_source", quote_source)
        if quote_age_sec is not None:
            top_candidate.setdefault("quote_age_sec", quote_age_sec)
        if row.get("feature_cutoff_ts") not in (None, "", "None"):
            top_candidate.setdefault("feature_cutoff_ts", row.get("feature_cutoff_ts"))
        if row.get("earliest_entry_ts") not in (None, "", "None"):
            top_candidate.setdefault("earliest_entry_ts", row.get("earliest_entry_ts"))
        if row_oos_context.get("is_oos") not in (None, "", "None"):
            top_candidate.setdefault("is_oos", row_oos_context.get("is_oos"))
        if row_oos_context.get("oos_label") not in (None, "", "None"):
            top_candidate.setdefault("oos_label", row_oos_context.get("oos_label"))
        if row_oos_context.get("oos_source") not in (None, "", "None"):
            top_candidate.setdefault("oos_source", row_oos_context.get("oos_source"))
        if row_oos_context.get("partition_id") not in (None, "", "None"):
            top_candidate.setdefault("partition_id", row_oos_context.get("partition_id"))
        if row_oos_context.get("split_name") not in (None, "", "None"):
            top_candidate.setdefault("split_name", row_oos_context.get("split_name"))
        top_candidate.setdefault("created_at", _iso_utc_from_epoch(ts_epoch))
        top_candidate.setdefault("trade_id", top_candidate.get("candidate_id") or top_candidate.get("strategy_id"))
        top_candidate.setdefault("candidate_id", top_candidate.get("trade_id"))
        top_candidate.setdefault("strategy_id", top_candidate.get("strategy_id") or strategy_id or "")
        top_candidate.setdefault("symbol", symbol)
        top_candidate.setdefault("replay_only", True)
        top_candidate.setdefault("broker_api_called", False)
        top_candidate.setdefault("order_action", False)
        top_candidate.setdefault("live_feed_used", False)
        top_candidate.setdefault("append", False)
        top_candidate.setdefault("output_isolated", True)
        top_candidate.setdefault("production_artifacts_written", bool(write_production_artifacts))

        try:
            handoff_payload = _report_to_handoff_payload(report, top_candidate)
            handoff_payload["signal_ts"] = top_candidate.get("signal_ts")
            handoff_payload["quote_source"] = top_candidate.get("quote_source")
            handoff_payload["quote_age_sec"] = top_candidate.get("quote_age_sec")
            handoff_payload["feature_cutoff_ts"] = top_candidate.get("feature_cutoff_ts")
            handoff_payload["earliest_entry_ts"] = top_candidate.get("earliest_entry_ts")
            handoff_payload["is_oos"] = top_candidate.get("is_oos")
            handoff_payload["oos_label"] = top_candidate.get("oos_label")
            handoff_payload["oos_source"] = top_candidate.get("oos_source")
            handoff_payload["partition_id"] = top_candidate.get("partition_id")
            handoff_payload["split_name"] = top_candidate.get("split_name")
            handoff_payload["replay_only"] = True
            handoff_payload["broker_api_called"] = False
            handoff_payload["order_action"] = False
            handoff_payload["live_feed_used"] = False
            handoff_payload["append"] = False
            handoff_payload["output_isolated"] = True
            handoff_payload["production_artifacts_written"] = bool(write_production_artifacts)
            write_runtime_candidate_handoff_evidence(
                path=handoff_path if not write_production_artifacts else Path(".runtime") / "runtime_candidate_handoff_latest.json",
                symbol=symbol,
                trade_builder_raw_count=int(getattr(report, "raw_candidate_count", 0) or 0),
                post_scan_survivor_count=int(getattr(report, "rankable_candidates", 0) or 0),
                post_soft_reject_count=int(getattr(report, "suppressed_rank_count", 0) or 0),
                post_real_filter_count=int(getattr(report, "normalized_candidate_count", 0) or 0),
                post_executable_filter_count=int(getattr(report, "executable_rank_count", 0) or 0),
                ranked_total_count=int(getattr(report, "ranked_candidate_count", 0) or 0),
                ranked_executable_count=int(getattr(report, "executable_rank_count", 0) or 0),
                top_reportable_executable=handoff_payload,
                cycle_ranked_candidates_count_before_append=0,
                cycle_ranked_candidates_count_after_append=1,
                phase2_input_count=int(getattr(report, "raw_candidate_count", 0) or 0),
                top_opportunities_payload={
                    "source_candidate_count": int(getattr(report, "raw_candidate_count", 0) or 0),
                    "top_executable_count": int(getattr(report, "executable_rank_count", 0) or 0),
                    "phase2_state": "REPLAY_ONLY",
                    "selector_outcome": "EXECUTE_TOP",
                },
                generated_epoch=float(ts_epoch if ts_epoch is not None else getattr(report, "generated_epoch", 0.0) or 0.0),
            )
            journal_row = dict(top_candidate)
            if row_oos_context:
                journal_row.update(row_oos_context)
            write_candidate_journal_row(
                journal_row,
                journal_event="candidate_reported",
                created_at=journal_row.get("created_at"),
                path=journal_path if not write_production_artifacts else Path(".runtime") / "candidates" / "candidate_journal.jsonl",
            )
        except Exception as exc:
            stage_evidence.append(_stage("persistence", False, source_path.name, top_candidate.get("trade_id"), f"{type(exc).__name__}:{exc}"))
            return _blocked_result(
                verdict="BLOCKED_NO_PERSISTENCE",
                blocker="BLOCKED_NO_PERSISTENCE",
                stage_evidence=tuple(stage_evidence),
                output_root=output_root,
                run_id=run_id,
                write_production_artifacts=write_production_artifacts,
                replay_event_id=replay_event_id,
                handoff_path=handoff_path,
                journal_path=journal_path,
                audit_json_path=audit_json_path,
                audit_md_path=audit_md_path,
            )

        stage_evidence.append(_stage("persistence", True, str(handoff_path), top_candidate.get("trade_id"), "ok"))
        selected_result = ReplayCandidateHandoffResult(
            verdict="FULLY_PROVEN_FROM_REPLAY_INPUT",
            replay_event_id=replay_event_id,
            blocker=None,
            blockers=(),
            stage_evidence=tuple(stage_evidence),
            replay_only_flag=REPLAY_ONLY_TRUE,
            broker_api_called_flag=BROKER_API_CALLED_FALSE,
            order_action_flag=ORDER_ACTION_FALSE,
            live_feed_used_flag=LIVE_FEED_USED_FALSE,
            append_flag=APPEND_FALSE,
            output_isolated_flag=OUTPUT_ISOLATED_TRUE,
            production_artifacts_written_flag=bool(write_production_artifacts),
            output_dir=str(run_dir),
            handoff_path=str(handoff_path),
            journal_path=str(journal_path),
            audit_json_path=str(audit_json_path),
            audit_md_path=str(audit_md_path),
        )
        break

    if selected_result is None:
        if last_ranked_blocker and last_ranked_blocker.get("verdict") == "BLOCKED_RANKING_REJECTED":
            verdict = "BLOCKED_RANKING_REJECTED"
            blocker = "BLOCKED_RANKING_REJECTED"
        elif any(stage["stage"] == "candidate" and stage["verdict"] == "BLOCKED_NO_CANDIDATE" for stage in stage_evidence):
            verdict = "BLOCKED_NO_CANDIDATE"
            blocker = "BLOCKED_NO_CANDIDATE"
        else:
            verdict = "BLOCKED_NO_CANDIDATE"
            blocker = "BLOCKED_NO_CANDIDATE"
        selected_result = ReplayCandidateHandoffResult(
            verdict=verdict,
            replay_event_id=replay_event_id,
            blocker=blocker,
            blockers=tuple(dict.fromkeys([stage.get("verdict") for stage in stage_evidence if stage.get("verdict") and stage.get("verdict").startswith("BLOCKED_")])) or (blocker,),
            stage_evidence=tuple(stage_evidence),
            replay_only_flag=REPLAY_ONLY_TRUE,
            broker_api_called_flag=BROKER_API_CALLED_FALSE,
            order_action_flag=ORDER_ACTION_FALSE,
            live_feed_used_flag=LIVE_FEED_USED_FALSE,
            append_flag=APPEND_FALSE,
            output_isolated_flag=OUTPUT_ISOLATED_TRUE,
            production_artifacts_written_flag=bool(write_production_artifacts),
            output_dir=str(run_dir),
            handoff_path=str(handoff_path) if handoff_path.exists() else None,
            journal_path=str(journal_path) if journal_path.exists() else None,
            audit_json_path=str(audit_json_path),
            audit_md_path=str(audit_md_path),
        )

    payload = selected_result.to_dict()
    if explicit_oos_context is not None:
        payload["oos_context"] = dict(explicit_oos_context)
    _write_audit_report(audit_json_path, payload)
    audit_md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return selected_result


def _stage(stage: str, proven: bool, source: str, object_id: Any, notes: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "verdict": "PROVEN" if proven else "BLOCKED",
        "evidence_source": source,
        "object_id": object_id,
        "notes": notes,
    }


def _blocked_result(
    *,
    verdict: str,
    blocker: str,
    stage_evidence: Iterable[dict[str, Any]],
    output_root: Path | None,
    run_id: str | None,
    write_production_artifacts: bool,
    replay_event_id: str | None = None,
    handoff_path: Path | None = None,
    journal_path: Path | None = None,
    audit_json_path: Path | None = None,
    audit_md_path: Path | None = None,
) -> ReplayCandidateHandoffResult:
    output_root = output_root or (Path(".runtime") / "replay_candidate_handoff")
    run_id = run_id or "blocked"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    audit_json_path = audit_json_path or (run_dir / "replay_candidate_handoff_audit.json")
    audit_md_path = audit_md_path or (run_dir / "replay_candidate_handoff_audit.md")
    result = ReplayCandidateHandoffResult(
        verdict=verdict,
        replay_event_id=replay_event_id,
        blocker=blocker,
        blockers=(blocker,),
        stage_evidence=tuple(stage_evidence),
        replay_only_flag=REPLAY_ONLY_TRUE,
        broker_api_called_flag=BROKER_API_CALLED_FALSE,
        order_action_flag=ORDER_ACTION_FALSE,
        live_feed_used_flag=LIVE_FEED_USED_FALSE,
        append_flag=APPEND_FALSE,
        output_isolated_flag=OUTPUT_ISOLATED_TRUE,
        production_artifacts_written_flag=bool(write_production_artifacts),
        output_dir=str(run_dir),
        handoff_path=str(handoff_path) if handoff_path else None,
        journal_path=str(journal_path) if journal_path else None,
        audit_json_path=str(audit_json_path),
        audit_md_path=str(audit_md_path),
    )
    payload = result.to_dict()
    _write_audit_report(audit_json_path, payload)
    audit_md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return result


__all__ = [
    "APPEND_FALSE",
    "BROKER_API_CALLED_FALSE",
    "LIVE_FEED_USED_FALSE",
    "ORDER_ACTION_FALSE",
    "OUTPUT_ISOLATED_TRUE",
    "PRODUCTION_ARTIFACTS_WRITTEN_FALSE",
    "REPLAY_FAILURE_BLOCKERS",
    "ReplayCandidateHandoffResult",
    "REPLAY_ONLY_TRUE",
    "run_replay_candidate_handoff",
]
