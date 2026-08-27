from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from config import config as cfg
from core.advisory_schema import AdvisorySchemaError, log_advisory_schema_error, serialize_advisory_row
from core.feed_health_truth import classify_feed_health_truth
from core.learning_paths import canonical_suggestions_log_path
from core.jsonl_tail_cache import tail_jsonl_rows as cached_tail_jsonl_rows
from core.market_snapshot_store import DEFAULT_MARKET_SNAPSHOT_PATH, read_market_snapshot
from core.paths import logs_dir, runtime_dir
from core.time_utils import is_today_local, now_ist

from core.ranking_orchestrator import build_ranked_opportunity_report
from core.movement_contract import StrategyContext
from core.runtime_cycle_context import RuntimeCycleContext, StageTiming
from core.runtime_snapshot_store import write_ranked_pipeline_snapshot, write_ranked_vs_legacy_snapshot
from core.runtime_snapshot_store import (
    ADVISORY_LATEST_PATH,
    FEED_RUNTIME_LATEST_PATH,
    MARKET_SNAPSHOT_PATH,
    TOKEN_RESOLUTION_LATEST_PATH,
    write_snapshot_atomic,
)
from core.observability import ObservabilityMetricsRegistry, build_default_metrics_registry
from core.runtime_authority_cutover import apply_runtime_authority, authority_allows_execution
from core.runtime_snapshot_stages import (
    build_advisory_latest_payload as stages_build_advisory_latest_payload,
    build_feed_health_truth_latest_payload as stages_build_feed_health_truth_latest_payload,
)
from core.feed.artifact_loader import load_current_feed_runtime


logger = logging.getLogger(__name__)

FEED_HEALTH_TRUTH_LATEST_PATH = runtime_dir() / "feed_health_truth_latest.json"
FEED_HEALTH_TRUTH_SNAPSHOT_SCHEMA_VERSION = 1


def _read_json_payload(path: Path) -> tuple[Any, list[str]]:
    notes: list[str] = []
    if not path.exists():
        notes.append(f"missing:{path}")
        return {"missing": True, "source_path": str(path)}, notes
    try:
        return json.loads(path.read_text(encoding="utf-8")), notes
    except Exception as exc:
        notes.append(f"parse_error:{path}:{type(exc).__name__}")
        return {
            "missing": False,
            "parse_error": f"{type(exc).__name__}:{exc}",
            "source_path": str(path),
        }, notes


def _tail_jsonl_rows(path: Path, limit: int = 200) -> list[str]:
    return cached_tail_jsonl_rows(path, limit=limit, namespace="runtime_snapshot_producer")


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        out = float(value)
    except Exception:
        return default
    if out != out:
        return default
    return float(out)


def _candidate_decisions_log_path() -> Path:
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT").strip() or "DEFAULT"
    return logs_dir() / "desks" / desk_id / "candidate_decisions.jsonl"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _regime_policy_context(data: dict[str, Any]) -> dict[str, Any]:
    regime = data.get("regime") if isinstance(data.get("regime"), dict) else {}
    feature_quality = _first_present(
        regime.get("feature_quality"),
        data.get("feature_quality"),
    )
    context = {
        "session_bucket": _first_present(
            regime.get("session_bucket"),
            data.get("session_bucket"),
        ),
        "regime_entropy": _first_present(
            regime.get("regime_entropy"),
            regime.get("entropy"),
            data.get("regime_entropy"),
        ),
        "regime_entropy_normalized": _first_present(
            regime.get("regime_entropy_normalized"),
            regime.get("normalized_entropy"),
            data.get("regime_entropy_normalized"),
        ),
        "regime_entropy_state": _first_present(
            regime.get("regime_entropy_state"),
            regime.get("entropy_state"),
            data.get("regime_entropy_state"),
        ),
        "regime_status": _first_present(
            regime.get("regime_status"),
            data.get("regime_status"),
        ),
        "primary_regime": _first_present(
            regime.get("primary_regime"),
            data.get("primary_regime"),
            data.get("regime_hint"),
        ),
        "stable_regime": _first_present(
            regime.get("stable_regime"),
            data.get("stable_regime"),
        ),
        "stable_regime_confirmed": _safe_bool(
            _first_present(
                regime.get("stable_regime_confirmed"),
                data.get("stable_regime_confirmed"),
            )
        ),
        "trend_state": _first_present(
            regime.get("trend_state"),
            data.get("trend_state"),
        ),
        "is_expiry_day": _safe_bool(
            _first_present(
                regime.get("is_expiry_day"),
                data.get("is_expiry_day"),
            )
        ),
        "volume_impulse": _safe_bool(
            _first_present(
                regime.get("volume_impulse"),
                data.get("volume_impulse"),
            )
        ),
        "liquidity_quality": _first_present(
            data.get("liquidity_quality"),
            (data.get("option_chain_summary") or {}).get("liquidity_quality"),
        ),
        "model_source": _first_present(
            regime.get("model_source"),
            data.get("model_source"),
        ),
        "model_hash": _first_present(
            regime.get("model_hash"),
            data.get("model_hash"),
        ),
        "probability_calibrated": _safe_bool(
            _first_present(
                regime.get("probability_calibrated"),
                data.get("probability_calibrated"),
            )
        ),
        "probability_semantics": _first_present(
            regime.get("probability_semantics"),
            data.get("probability_semantics"),
        ),
        "regime_top_two_margin": _first_present(
            regime.get("regime_top_two_margin"),
            regime.get("top_two_margin"),
            data.get("regime_top_two_margin"),
        ),
        "feature_quality": feature_quality if isinstance(feature_quality, dict) else None,
    }
    return {key: value for key, value in context.items() if value is not None}


def _strategy_context_from_market_symbol(symbol: str, data: dict[str, Any]) -> StrategyContext:
    allowed = {field.name for field in dataclass_fields(StrategyContext)}
    payload: dict[str, Any] = {"symbol": str(symbol or "").strip().upper() or "UNKNOWN"}
    payload["spot_ltp"] = data.get("spot_ltp", data.get("ltp", data.get("spot")))
    payload["vwap"] = (data.get("ohlc") or {}).get("close", data.get("vwap"))
    payload["day_high"] = (data.get("ohlc") or {}).get("high", data.get("day_high"))
    payload["day_low"] = (data.get("ohlc") or {}).get("low", data.get("day_low"))
    payload["open_price"] = (data.get("ohlc") or {}).get("open", data.get("open_price"))
    payload["regime_hint"] = (data.get("regime") or {}).get("primary_regime", data.get("regime_hint"))
    payload["regime_scores"] = dict((data.get("regime") or {}).get("scores") or data.get("regime_scores") or {})
    payload["ce_spread_pct"] = (data.get("option_chain_summary") or {}).get("ce_spread_pct", data.get("ce_spread_pct"))
    payload["pe_spread_pct"] = (data.get("option_chain_summary") or {}).get("pe_spread_pct", data.get("pe_spread_pct"))
    payload["ce_depth"] = (data.get("option_chain_summary") or {}).get("ce_depth", data.get("ce_depth"))
    payload["pe_depth"] = (data.get("option_chain_summary") or {}).get("pe_depth", data.get("pe_depth"))
    payload["option_ce_ltp"] = (data.get("option_chain_summary") or {}).get("ce_ltp", data.get("option_ce_ltp"))
    payload["option_pe_ltp"] = (data.get("option_chain_summary") or {}).get("pe_ltp", data.get("option_pe_ltp"))
    payload["quote_source"] = (data.get("feed_health") or {}).get("quote_source", data.get("quote_source"))
    payload["fallback_used"] = (data.get("feed_health") or {}).get("fallback_used", data.get("fallback_used"))
    payload["option_ltp_age_sec"] = (data.get("feed_health") or {}).get("option_ltp_age_sec", data.get("option_ltp_age_sec"))
    payload["ts_epoch"] = data.get("ts_epoch")
    metadata = dict(data.get("metadata") or {})
    policy_context = _regime_policy_context(data)
    if policy_context:
        metadata["regime_policy_context"] = policy_context
    payload["metadata"] = metadata
    payload["evidence"] = dict(data.get("evidence") or {})
    payload["lineage"] = dict(data.get("lineage") or {"source": "market_snapshot"})
    filtered = {key: value for key, value in payload.items() if key in allowed and value is not None}
    return StrategyContext(**filtered)


def _row_snapshot_timestamp(row: dict[str, Any]) -> Any:
    if not isinstance(row, dict):
        return None
    for key in (
        "display_ts_epoch",
        "decision_ts_epoch",
        "snapshot_ts_epoch",
        "created_ts_epoch",
        "last_seen_ts_epoch",
        "timestamp_epoch",
        "ts_epoch",
        "timestamp",
        "ts_ist",
        "last_seen_ts",
        "last_seen",
    ):
        value = row.get(key)
        if value not in (None, "", "None"):
            return value
    return None


def _row_is_today_local(row: dict[str, Any]) -> bool:
    ts_value = _row_snapshot_timestamp(row)
    if ts_value in (None, "", "None"):
        return False
    try:
        return is_today_local(ts_value, now=now_ist())
    except Exception:
        return False


def _feed_health_symbols(feed_payload: Any) -> tuple[str, ...]:
    if not isinstance(feed_payload, dict):
        return ()
    symbols: set[str] = set()
    for key in (
        "option_feed_block_reason_by_symbol",
        "option_last_tick_age_by_symbol",
        "symbol_feed_ok_by_symbol",
        "feed_ok_by_symbol",
    ):
        values = feed_payload.get(key)
        if not isinstance(values, dict):
            continue
        symbols.update(str(symbol or "").strip().upper() for symbol in values if str(symbol or "").strip())
    return tuple(sorted(symbols))


def _build_feed_health_truth_latest_payload(feed_payload: Any) -> tuple[dict[str, Any], Any]:
    payload, _decision = stages_build_feed_health_truth_latest_payload(feed_payload)
    return payload


def _build_advisory_latest_payload(limit: int = 200) -> dict[str, Any]:
    path = canonical_suggestions_log_path()
    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    for raw_line in _tail_jsonl_rows(path, limit=limit):
        try:
            payload = json.loads(raw_line)
        except Exception as exc:
            notes.append(f"parse_error:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            notes.append("row_not_object")
            continue
        try:
            row = serialize_advisory_row(payload, allow_legacy=True)
            if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)) and not _row_is_today_local(row):
                notes.append(
                    f"stale_row_dropped:{str(row.get('trade_id') or row.get('advisory_id') or 'unknown')}"
                )
                logger.info(
                    "[RUNTIME_SNAPSHOT_ROW_DROP] source=advisory_latest reason=stale_row trade_id=%s symbol=%s display_ts_epoch=%s",
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("display_ts_epoch"),
                )
                continue
            rows.append(row)
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("runtime_snapshot_producer", payload, exc)
            notes.append(f"schema_error:{exc}")
    if rows:
        return {
            "rows": rows,
            "row_count": int(len(rows)),
            "source_path": str(path),
            "notes": notes,
        }
    if not bool(getattr(cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", True)):
        return {
            "rows": rows,
            "row_count": int(len(rows)),
            "source_path": str(path),
            "notes": notes,
        }

    fallback_path = _candidate_decisions_log_path()
    fallback_rows: list[dict[str, Any]] = []
    fallback_notes: list[str] = []
    for raw_line in _tail_jsonl_rows(fallback_path, limit=max(1, int(getattr(cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_LIMIT", limit)))):
        try:
            payload = json.loads(raw_line)
        except Exception as exc:
            fallback_notes.append(f"fallback_parse_error:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            fallback_notes.append("fallback_row_not_object")
            continue
        try:
            row = _candidate_decision_to_advisory_row(payload)
            if row is None:
                fallback_notes.append(
                    f"fallback_row_dropped:{str(payload.get('candidate_id') or payload.get('trade_id') or 'unknown')}"
                )
                continue
            if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)) and not _row_is_today_local(row):
                fallback_notes.append(
                    f"fallback_stale_row_dropped:{str(row.get('trade_id') or row.get('advisory_id') or 'unknown')}"
                )
                logger.info(
                    "[RUNTIME_SNAPSHOT_ROW_DROP] source=advisory_latest reason=fallback_stale_row trade_id=%s symbol=%s display_ts_epoch=%s",
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("display_ts_epoch"),
                )
                continue
            fallback_rows.append(row)
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("runtime_snapshot_producer.candidate_decisions", payload, exc)
            fallback_notes.append(f"fallback_schema_error:{exc}")
    notes.append(f"fallback_source:{fallback_path}")
    notes.extend(fallback_notes)
    return {
        "rows": fallback_rows,
        "row_count": int(len(fallback_rows)),
        "source_path": str(fallback_path),
        "notes": notes,
    }


def _candidate_decision_to_advisory_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    candidate_id = str(payload.get("candidate_id") or payload.get("trade_id") or "").strip()
    symbol = str(payload.get("symbol") or "").strip().upper()
    ts_epoch = _row_snapshot_timestamp(payload)
    entry = _safe_float(payload.get("entry"))
    if not candidate_id or not symbol or entry is None:
        return None
    source_flags = payload.get("source_flags") if isinstance(payload.get("source_flags"), dict) else {}
    candidate_origin = source_flags.get("candidate_origin") if isinstance(source_flags, dict) and isinstance(source_flags.get("candidate_origin"), dict) else {}
    strategy_id = (
        str(candidate_origin.get("setup_family") or candidate_origin.get("strategy") or payload.get("strategy_id") or "LIVE_CANDIDATE")
        .strip()
        or "LIVE_CANDIDATE"
    )
    strategy_name = (
        str(payload.get("strategy_name") or candidate_origin.get("setup_family") or payload.get("strategy_id") or "LIVE_CANDIDATE")
        .strip()
        or "LIVE_CANDIDATE"
    )
    execution_allowed = bool(payload.get("execution_allowed"))
    permission = str(payload.get("permission") or ("EXECUTE" if execution_allowed else "ADVISORY_ONLY")).strip().upper() or "ADVISORY_ONLY"
    final_action = str(payload.get("final_action") or ("EXECUTE" if execution_allowed else "QUEUE_ONLY")).strip().upper() or "QUEUE_ONLY"
    if execution_allowed:
        execution_entry = entry
        execution_entry_source = "last"
        execution_entry_status = "executable"
        readiness = "READY"
        execution_status = "executable"
    else:
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "non_executable"
        readiness = "QUEUE_ONLY" if permission != "ADVISORY_ONLY" else "ADVISORY_ONLY"
        execution_status = final_action.lower()
        if execution_status not in {"blocked", "advisory_only", "queue_only", "executable", "scored"}:
            execution_status = "queue_only"
    advisory_payload = dict(payload)
    advisory_payload.update(
        {
            "trade_id": candidate_id,
            "advisory_id": candidate_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "timestamp": payload.get("ts_ist") or payload.get("timestamp") or payload.get("ts_epoch") or "",
            "instrument_type": "OPT",
            "entry": entry,
            "entry_source": "last",
            "execution_entry": execution_entry,
            "execution_entry_source": execution_entry_source,
            "execution_entry_status": execution_entry_status,
            "display_entry": entry,
            "display_entry_source": "last",
            "display_entry_status": "displayable",
            "entry_reason": str(payload.get("permission_reason") or payload.get("entry_block_reason") or payload.get("first_blocking_gate") or payload.get("final_action") or "candidate_decision"),
            "entry_clear_reason": str(payload.get("entry_block_reason") or payload.get("quote_validation_status") or payload.get("first_blocking_gate") or "candidate_decision"),
            "entry_status": "displayable",
            "readiness": readiness,
            "blockers": list(payload.get("gates_failed") or ([] if execution_allowed else [payload.get("first_blocking_gate") or payload.get("permission_reason") or "candidate_decision"])),
            "hard_blockers": list(payload.get("gates_failed") or []),
            "soft_penalties": list(payload.get("soft_vetos") or []),
            "warnings": list(payload.get("gates_failed") or []),
            "quote_source": str(source_flags.get("ltp_source") or "live"),
            "quote_age_sec": _safe_float(source_flags.get("quote_age_sec")),
            "decision_explain": [
                str(value)
                for value in (
                    payload.get("first_blocking_gate"),
                    payload.get("permission_reason"),
                    payload.get("quote_validation_status"),
                    payload.get("final_action"),
                )
                if str(value or "").strip()
            ],
            "market_open": bool(source_flags.get("market_open", True)),
            "execution_status": execution_status,
            "permission": permission,
            "final_action": final_action,
        }
    )
    advisory_payload.setdefault("display_ts_epoch", ts_epoch)
    advisory_payload.setdefault("display_ts_ist", payload.get("ts_ist"))
    advisory_payload.setdefault("last_seen_ts", payload.get("ts_ist") or payload.get("timestamp"))
    advisory_payload.setdefault("last_seen", payload.get("ts_ist") or payload.get("timestamp"))
    advisory_payload.setdefault("trade_key", payload.get("candidate_id"))
    advisory_payload.setdefault("instrument", "OPT")
    advisory_payload.setdefault("status", "ADVISORY_ONLY" if not execution_allowed else "READY")
    advisory_payload.setdefault("candidate_status", payload.get("candidate_status") or "LIVE_CANDIDATE")
    advisory_payload.setdefault("candidate_type", payload.get("candidate_type") or "options")
    advisory_payload.setdefault("strategy", strategy_name)
    advisory_payload.setdefault("source_bucket", "candidate_decisions")
    advisory_payload.setdefault("row_kind", "canonical_suggestion")
    advisory_payload.setdefault("non_canonical_levels", False)
    advisory_payload = apply_runtime_authority(
        advisory_payload,
        mode=str(payload.get("mode") or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"),
    )
    if not execution_allowed:
        advisory_payload["execution_allowed"] = False
        advisory_payload["eligible_for_execution"] = False
        advisory_payload["selected_for_execution"] = False
        advisory_payload["execution_entry"] = None
        advisory_payload["execution_entry_source"] = "none"
        advisory_payload["execution_entry_status"] = "non_executable"
        advisory_payload["execution_status"] = execution_status
        advisory_payload["readiness"] = readiness
    return serialize_advisory_row(advisory_payload, allow_legacy=True)


def _build_and_write_canonical_ranked_snapshot(
    market_payload: dict,
    producer: str,
    advisory_payload: dict,
    *,
    cycle_context: RuntimeCycleContext | None = None,
):
    from core.canonical_ranked_ui_adapter import adapt_candidate_rank_record_to_ui
    reports = []
    top_executable = []
    top_advisory = []
    symbols = market_payload.get("symbols") or {}

    canonical_top_strategy_id = None
    canonical_ranked_count = 0
    recovered_fallback_in_canonical_executable = False
    stale_or_untrusted_quote_in_canonical_executable = False

    for sym, data in symbols.items():
        if not isinstance(data, dict):
            continue
        try:
            ctx_data = dict(data)
            ctx_data["symbol"] = sym
            ctx_data.setdefault("spot_ltp", (data.get("ohlc") or {}).get("close") or 0.0)
            ctx = _strategy_context_from_market_symbol(sym, ctx_data)
            report = build_ranked_opportunity_report(ctx=ctx, cycle_context=cycle_context, feed_health=cycle_context.feed_truth if cycle_context else None)
            reports.append(report.to_dict())

            if not canonical_top_strategy_id and report.top_rank_strategy_id:
                canonical_top_strategy_id = report.top_rank_strategy_id

            canonical_ranked_count += report.ranked_candidate_count

            for rank in report.ranking.ranks:
                rank_dict = rank.to_dict()
                rank_dict["ranked_report_id"] = getattr(report.ranking, "ranked_report_id", None)
                rank_dict["generated_epoch"] = report.generated_epoch
                row = adapt_candidate_rank_record_to_ui(rank_dict)
                row = apply_runtime_authority(
                    row,
                    mode=str(getattr(cfg, 'EXECUTION_MODE', 'SIM') or 'SIM'),
                )

                # Check for fake entry prices (Point 3)
                has_entry = rank.outcome_contract and rank.outcome_contract.entry_price
                if has_entry:
                    row["entry"] = rank.outcome_contract.entry_price
                    row["display_entry"] = row["entry"]

                # Executable classification (Point 2)
                if authority_allows_execution(row) and has_entry:
                    row["execution_status"] = "executable"
                    row["readiness"] = "READY"
                    top_executable.append(row)

                    if "FALLBACK" in rank.safety_flags:
                        recovered_fallback_in_canonical_executable = True
                    if "STALE" in rank.safety_flags or "UNTRUSTED" in rank.safety_flags:
                        stale_or_untrusted_quote_in_canonical_executable = True
                else:
                    if rank.bucket == "NEAR_EXECUTABLE_CANDIDATE":
                        row["execution_status"] = "queue_only"
                        row["readiness"] = "ADVISORY_ONLY"
                    row["entry_status"] = "displayable" if has_entry else "non_executable"
                    top_advisory.append(row)

                row["display_ts_epoch"] = report.generated_epoch * 1000.0
                row["timestamp"] = report.generated_epoch * 1000.0
                row["confidence"] = rank.outcome_contract.confidence_score if rank.outcome_contract else 0.0

        except Exception as exc:
            logger.warning(f"canonical_pipeline_failed_for_symbol symbol={sym} error={exc}")
            continue

    payload = {
        "top_executable": top_executable,
        "top_advisory": top_advisory,
        "reports": reports,
        "source": "ranked_opportunity_pipeline_v1"
    }
    write_ranked_pipeline_snapshot(payload=payload, producer=producer)

    # Ranked vs Legacy Comparison Evidence (Point 4)
    legacy_rows = advisory_payload.get("rows", [])
    legacy_top_count = len(legacy_rows)
    legacy_top_strategy_id = legacy_rows[0].get("strategy_id") if legacy_rows else None

    recovered_fallback_in_legacy_top = any(r.get("recovered_fallback") for r in legacy_rows)
    mismatch_detected = (legacy_top_strategy_id != canonical_top_strategy_id)

    if recovered_fallback_in_canonical_executable or stale_or_untrusted_quote_in_canonical_executable:
        verdict = "FAIL"
    elif mismatch_detected:
        verdict = "WARN"
    else:
        verdict = "PASS"

    comparison_evidence = {
        "legacy_top_count": legacy_top_count,
        "canonical_ranked_count": canonical_ranked_count,
        "legacy_top_strategy_id": legacy_top_strategy_id,
        "canonical_top_strategy_id": canonical_top_strategy_id,
        "mismatch_detected": mismatch_detected,
        "recovered_fallback_in_legacy_top": recovered_fallback_in_legacy_top,
        "recovered_fallback_in_canonical_executable": recovered_fallback_in_canonical_executable,
        "stale_or_untrusted_quote_in_canonical_executable": stale_or_untrusted_quote_in_canonical_executable,
        "verdict": verdict
    }
    write_ranked_vs_legacy_snapshot(payload=comparison_evidence, producer=producer)
    return payload


def produce_and_store_runtime_snapshots(
    *,
    market_snapshot: dict[str, Any] | None,
    producer: str,
    loop_id: str | None = None,
    metrics_registry: ObservabilityMetricsRegistry | None = None,
    cycle_feed_truth_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    timings: list[dict[str, Any]] = []
    cycle_started = time.perf_counter()

    market_payload = market_snapshot
    if not isinstance(market_payload, dict):
        try:
            market_payload = read_market_snapshot(DEFAULT_MARKET_SNAPSHOT_PATH)
        except Exception as exc:
            market_payload = {"missing": True, "error": f"{type(exc).__name__}:{exc}"}
    if isinstance(market_payload, dict) and (
        market_payload.get("missing") or (isinstance(market_payload.get("payload"), dict) and market_payload["payload"].get("missing"))
    ):
        from core.live_market_snapshot_producer import build_live_market_snapshot
        market_payload = build_live_market_snapshot(
            db_path=runtime_dir() / "db" / "DEFAULT.sqlite",
            output_path=DEFAULT_MARKET_SNAPSHOT_PATH,
            instrument_path=runtime_dir() / "instruments.raw.json",
            session_id=str(os.environ.get("RUN_ID") or loop_id or "canonical-live"),
            session_date=now_ist().date().isoformat(),
            source_sha=str(os.environ.get("TRADEBOT_COMMIT_SHA") or ""),
        )
    outputs["market_snapshot"] = market_payload

    advisory_payload = _build_advisory_latest_payload()
    outputs["advisory_latest"] = advisory_payload

    t1 = time.perf_counter()
    loaded_runtime = load_current_feed_runtime(logs_dir() / "feed_runtime_latest.json")
    feed_payload = dict(loaded_runtime.get("payload") or {}) if loaded_runtime.get("valid") else None
    _feed_notes = [] if loaded_runtime.get("valid") else [str(loaded_runtime.get("reason_code") or "canonical_feed_runtime_invalid")]
    outputs["feed_runtime_latest"] = feed_payload
    shared_cycle_feed_truth = dict(cycle_feed_truth_payload or {})
    if shared_cycle_feed_truth:
        outputs["cycle_feed_truth_latest"] = dict(shared_cycle_feed_truth)
        feed_truth_payload = dict(shared_cycle_feed_truth)
        feed_truth_decision = type(
            "_SharedFeedTruthDecision",
            (),
            {"to_payload": lambda self: dict(shared_cycle_feed_truth)},
        )()
    else:
        feed_truth_payload, feed_truth_decision = stages_build_feed_health_truth_latest_payload(feed_payload)
    outputs["feed_health_truth_latest"] = feed_truth_payload
    try:
        from core.unified_live_validation_pr748_756.runtime_observer import safe_call

        safe_call(
            "observe_feed_truth",
            feed_truth_payload,
            source="core.runtime_snapshot_producer.feed_health_truth_latest",
        )
    except Exception:
        pass
    timings.append({"stage": "feed_health_truth", "elapsed_ms": round((time.perf_counter() - t1) * 1000.0, 3)})
    cycle_context = RuntimeCycleContext(
        cycle_id=str(loop_id or producer or "runtime_snapshot"),
        feed_truth=shared_cycle_feed_truth or feed_truth_decision.to_payload(),
        stage_timings=(
            StageTiming(
                stage="feed_health_truth",
                elapsed_ms=timings[-1]["elapsed_ms"],
                metadata={"producer": producer},
            ),
        ),
        metadata={"producer": producer, "shared_cycle_feed_truth": bool(shared_cycle_feed_truth)},
    )

    try:
        t2 = time.perf_counter()
        if isinstance(market_payload, dict):
            outputs["ranked_pipeline_latest"] = _build_and_write_canonical_ranked_snapshot(
                market_payload,
                producer,
                advisory_payload,
                cycle_context=cycle_context,
            )
        timings.append({"stage": "ranked_pipeline_snapshot", "elapsed_ms": round((time.perf_counter() - t2) * 1000.0, 3)})
    except Exception as exc:
        logger.error(f"failed_to_build_canonical_ranked_snapshot: {exc}")
        outputs["ranked_pipeline_latest"] = {}

    token_payload, _token_notes = _read_json_payload(logs_dir() / "token_resolution.json")
    outputs["token_resolution_latest"] = token_payload
    timings.append({"stage": "runtime_snapshot_producer_total", "elapsed_ms": round((time.perf_counter() - cycle_started) * 1000.0, 3)})
    outputs["runtime_cycle_timings"] = timings
    outputs["runtime_cycle_context"] = cycle_context.to_dict()
    try:
        from core.unified_live_validation_pr748_756.runtime_observer import safe_call

        safe_call(
            "observe_feed_truth",
            outputs["runtime_cycle_context"],
            source="core.runtime_snapshot_producer.runtime_cycle_context",
        )
    except Exception:
        pass
    registry = metrics_registry or build_default_metrics_registry()
    try:
        registry.observe_latency_ms(
            "tradebot_snapshot_producer_latency_ms",
            timings[-1]["elapsed_ms"] if timings else (time.perf_counter() - cycle_started) * 1000.0,
            labels={"producer": producer},
        )
        for item in timings:
            registry.observe_latency_ms(
                "tradebot_snapshot_stage_latency_ms",
                item["elapsed_ms"],
                labels={"producer": producer, "stage": str(item["stage"])},
            )
    except Exception as exc:
        logger.warning("snapshot_producer_metrics_emit_failed err=%s", exc)

    paths = {
        "market_snapshot": MARKET_SNAPSHOT_PATH,
        "advisory_latest": ADVISORY_LATEST_PATH,
        "feed_runtime_latest": FEED_RUNTIME_LATEST_PATH,
        "feed_health_truth_latest": FEED_HEALTH_TRUTH_LATEST_PATH,
        "token_resolution_latest": TOKEN_RESOLUTION_LATEST_PATH,
    }
    for name, path in paths.items():
        write_snapshot_atomic(path, payload=outputs[name], producer=producer)
        logger.info(
            "[RUNTIME_SNAPSHOT_WRITE] name=%s path=%s",
            name,
            path,
        )
    return outputs
