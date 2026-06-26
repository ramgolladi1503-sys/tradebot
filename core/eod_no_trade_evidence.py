from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EOD_NO_TRADE_EVIDENCE_SCHEMA_VERSION = 1
EOD_NO_TRADE_EVIDENCE_SOURCE = "eod_no_trade_evidence_v1"
DEFAULT_INDEX_SYMBOLS = ("NIFTY 50", "NIFTY BANK", "SENSEX", "INDIA VIX")
DEFAULT_REPLAY_KEYS = ("NIFTY_INDEX", "BANKNIFTY_INDEX", "SENSEX", "SENSEX_INDEX", "INDIA_VIX")


@dataclass(frozen=True)
class EODNoTradeEvidence:
    trade_date: str
    tick_integrity: dict[str, Any]
    replay_coverage: dict[str, Any]
    runtime_artifacts: dict[str, Any]
    wfa_proxy: dict[str, Any]
    conclusions: tuple[str, ...]
    warnings: tuple[str, ...]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    schema_version: int = EOD_NO_TRADE_EVIDENCE_SCHEMA_VERSION
    source: str = EOD_NO_TRADE_EVIDENCE_SOURCE
    read_only: bool = True

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["read_only"] = True
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        payload["append"] = False
        return payload


def build_eod_no_trade_evidence(
    *,
    trade_date: str,
    tick_path: str | Path,
    replay_path: str | Path,
    runtime_dir: str | Path = ".runtime",
    wfa_csv_path: str | Path | None = "data/oos_trades.csv",
    index_symbols: Sequence[str] = DEFAULT_INDEX_SYMBOLS,
    replay_keys: Sequence[str] = DEFAULT_REPLAY_KEYS,
) -> EODNoTradeEvidence:
    tick_integrity = analyze_tick_file(Path(tick_path), index_symbols=index_symbols)
    replay_coverage = analyze_replay_file(Path(replay_path), replay_keys=replay_keys)
    runtime_artifacts = summarize_runtime_artifacts(Path(runtime_dir))
    wfa_proxy = summarize_wfa_proxy(Path(wfa_csv_path)) if wfa_csv_path else _missing_summary(wfa_csv_path)
    warnings = tuple(_build_warnings(tick_integrity, replay_coverage, runtime_artifacts, wfa_proxy))
    conclusions = tuple(_build_conclusions(tick_integrity, replay_coverage, runtime_artifacts, wfa_proxy))
    return EODNoTradeEvidence(
        trade_date=trade_date,
        tick_integrity=tick_integrity,
        replay_coverage=replay_coverage,
        runtime_artifacts=runtime_artifacts,
        wfa_proxy=wfa_proxy,
        conclusions=conclusions,
        warnings=warnings,
    )


def analyze_tick_file(path: Path, *, index_symbols: Sequence[str] = DEFAULT_INDEX_SYMBOLS) -> dict[str, Any]:
    if not path.exists():
        return _missing_summary(path)

    first: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    records = 0
    bad_json = 0
    non_monotonic_ticks = 0
    previous_ts: float | None = None
    symbols: Counter[str] = Counter()
    index_counts: Counter[str] = Counter()
    index_set = set(index_symbols)

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                bad_json += 1
                continue
            if not isinstance(row, dict):
                bad_json += 1
                continue
            ts = _safe_float(row.get("ts"))
            if ts is not None:
                if previous_ts is not None and ts < previous_ts:
                    non_monotonic_ticks += 1
                previous_ts = ts
            if first is None:
                first = row
            last = row
            symbol = str(row.get("symbol") or "")
            if symbol:
                symbols[symbol] += 1
                if symbol in index_set:
                    index_counts[symbol] += 1
            records += 1

    present_index_symbols = tuple(symbol for symbol in index_symbols if index_counts.get(symbol, 0) > 0)
    missing_index_symbols = tuple(symbol for symbol in index_symbols if index_counts.get(symbol, 0) <= 0)
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "records": records,
        "bad_json_lines": bad_json,
        "non_monotonic_ticks": non_monotonic_ticks,
        "first_tick": _tick_summary(first),
        "last_tick": _tick_summary(last),
        "unique_symbol_count": len(symbols),
        "top_symbols": symbols.most_common(12),
        "index_counts": dict(index_counts),
        "present_index_symbols": present_index_symbols,
        "missing_index_symbols": missing_index_symbols,
        "structurally_usable": records > 0 and bad_json == 0 and non_monotonic_ticks == 0,
    }


def analyze_replay_file(path: Path, *, replay_keys: Sequence[str] = DEFAULT_REPLAY_KEYS) -> dict[str, Any]:
    if not path.exists():
        return _missing_summary(path)

    timestamp_pattern = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
    key_presence = {key: False for key in replay_keys}
    snapshot_count = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), ""):
            if not chunk:
                break
            for key in key_presence:
                if not key_presence[key] and key in chunk:
                    key_presence[key] = True
            for match in timestamp_pattern.finditer(chunk):
                snapshot_count += 1
                if first_timestamp is None:
                    first_timestamp = match.group(1)
                last_timestamp = match.group(1)

    missing_keys = tuple(key for key, present in key_presence.items() if not present)
    present_keys = tuple(key for key, present in key_presence.items() if present)
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "snapshot_count": snapshot_count,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
        "key_presence": key_presence,
        "diagnostic_only": True,
        "production_equivalent": False,
        "authority_warning": (
            "Replay coverage describes converted tick data only; it does not prove production decision "
            "equivalence unless a production orchestrator replay harness consumes the same file."
        ),
    }


def summarize_runtime_artifacts(runtime_dir: Path) -> dict[str, Any]:
    files = {
        "strategy_no_qualified": runtime_dir / "strategy_no_qualified_reasons_latest.json",
        "candidate_starvation": runtime_dir / "candidate_starvation_trace_latest.json",
        "phase2_rejection": runtime_dir / "phase2_rejection_latest.json",
        "notrade_reason_truth": runtime_dir / "notrade_reason_truth_latest.json",
    }
    summaries: dict[str, Any] = {}
    for name, path in files.items():
        payload = _read_json_dict(path)
        summaries[name] = _runtime_artifact_summary(path, payload)

    candidate = summaries["candidate_starvation"].get("payload_summary", {})
    phase2 = summaries["phase2_rejection"].get("payload_summary", {})
    strategy = summaries["strategy_no_qualified"].get("payload_summary", {})
    notrade = summaries["notrade_reason_truth"].get("payload_summary", {})

    return {
        "artifacts": summaries,
        "top_level_blockers": {
            "strategy_not_applicable_reason": strategy.get("not_applicable_reason"),
            "latest_global_blocker": candidate.get("latest_global_blocker"),
            "first_zero_stage": candidate.get("first_zero_stage"),
            "phase2_starvation_reason": phase2.get("phase2_starvation_reason"),
            "primary_reason": notrade.get("primary_reason"),
        },
        "phase2_input_candidate_count": _first_present(
            phase2.get("phase2_input_count"),
            strategy.get("phase2_input_candidate_count"),
            notrade.get("phase2_input_candidate_count"),
        ),
        "raw_candidate_count": _first_present(strategy.get("raw_candidate_count"), candidate.get("raw_candidate_count")),
        "complete_per_symbol_table_available": bool(strategy.get("by_symbol_keys") or candidate.get("by_symbol_keys")),
        "candidate_funnel_by_symbol": candidate.get("last_candidate_funnel_by_symbol") or {},
        "last_symbol_snapshot": candidate.get("last_symbol_snapshot") or {},
    }


def summarize_wfa_proxy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing_summary(path)

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    pnl_values = [_safe_float(row.get("pl")) or 0.0 for row in rows]
    trade_count = len(rows)
    strategy_counts: Counter[str] = Counter(row.get("strategy") or "unknown" for row in rows)
    year_counts: Counter[str] = Counter(row.get("test_year") or "unknown" for row in rows)
    outcome_counts: Counter[str] = Counter(row.get("outcome") or "unknown" for row in rows)
    is_oos_counts: Counter[str] = Counter(str(row.get("is_oos")) for row in rows)
    win_count = sum(1 for value in pnl_values if value > 0)
    total_pnl = sum(pnl_values)

    return {
        "path": str(path),
        "exists": True,
        "trade_count": trade_count,
        "total_pnl": round(total_pnl, 2),
        "win_rate_pct": round((win_count / trade_count) * 100.0, 2) if trade_count else None,
        "average_pnl": round(total_pnl / trade_count, 2) if trade_count else None,
        "strategy_counts": dict(strategy_counts),
        "test_year_counts": dict(year_counts),
        "outcome_counts": dict(outcome_counts),
        "is_oos_counts": dict(is_oos_counts),
        "proxy_only": True,
        "edge_claimed": False,
        "authority_warning": (
            "This CSV is proxy research unless produced from real option bid/ask truth and the production "
            "Phase 2 gate chain."
        ),
    }


def write_eod_no_trade_evidence(
    evidence: EODNoTradeEvidence,
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[Path, Path]:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(evidence.to_payload(), indent=2, sort_keys=True), encoding="utf-8")
    markdown_target.write_text(eod_no_trade_evidence_to_markdown(evidence), encoding="utf-8")
    return json_target, markdown_target


def eod_no_trade_evidence_to_markdown(evidence: EODNoTradeEvidence) -> str:
    payload = evidence.to_payload()
    tick = payload["tick_integrity"]
    replay = payload["replay_coverage"]
    runtime = payload["runtime_artifacts"]
    wfa = payload["wfa_proxy"]

    lines = [
        f"# EOD No-Trade Evidence: {payload['trade_date']}",
        "",
        "Scope: read-only evidence. No broker APIs called. No order actions taken.",
        "",
        "## Safety Flags",
        "",
        f"- `read_only`: `{payload['read_only']}`",
        f"- `is_order_action`: `{payload['is_order_action']}`",
        f"- `broker_api_called`: `{payload['broker_api_called']}`",
        f"- `live_order_action`: `{payload['live_order_action']}`",
        f"- `broker_order_action`: `{payload['broker_order_action']}`",
        "",
        "## Tick Integrity",
        "",
        f"- Records: `{tick.get('records')}`",
        f"- Non-monotonic ticks: `{tick.get('non_monotonic_ticks')}`",
        f"- Present index symbols: `{', '.join(tick.get('present_index_symbols') or ()) or 'none'}`",
        f"- Missing index symbols: `{', '.join(tick.get('missing_index_symbols') or ()) or 'none'}`",
        "",
        "## Replay Coverage",
        "",
        f"- Snapshots: `{replay.get('snapshot_count')}`",
        f"- First timestamp: `{replay.get('first_timestamp')}`",
        f"- Last timestamp: `{replay.get('last_timestamp')}`",
        f"- Present keys: `{', '.join(replay.get('present_keys') or ()) or 'none'}`",
        f"- Missing keys: `{', '.join(replay.get('missing_keys') or ()) or 'none'}`",
        f"- Production equivalent: `{replay.get('production_equivalent')}`",
        "",
        "## Runtime Blockers",
        "",
        f"- Top blockers: `{json.dumps(runtime.get('top_level_blockers', {}), sort_keys=True)}`",
        f"- Raw candidate count: `{runtime.get('raw_candidate_count')}`",
        f"- Phase 2 input candidate count: `{runtime.get('phase2_input_candidate_count')}`",
        f"- Complete per-symbol table available: `{runtime.get('complete_per_symbol_table_available')}`",
        "",
        "## WFA Proxy",
        "",
        f"- Trades: `{wfa.get('trade_count')}`",
        f"- Total PnL: `{wfa.get('total_pnl')}`",
        f"- Win rate pct: `{wfa.get('win_rate_pct')}`",
        f"- Proxy only: `{wfa.get('proxy_only')}`",
        f"- Edge claimed: `{wfa.get('edge_claimed')}`",
        "",
        "## Warnings",
        "",
    ]
    lines.extend(f"- {warning}" for warning in evidence.warnings)
    lines.extend(["", "## Conclusions", ""])
    lines.extend(f"- {conclusion}" for conclusion in evidence.conclusions)
    lines.append("")
    return "\n".join(lines)


def _runtime_artifact_summary(path: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"path": str(path), "exists": path.exists(), "payload_summary": {}}
    by_symbol = payload.get("by_symbol") if isinstance(payload.get("by_symbol"), Mapping) else {}
    summary = {
        "generated_epoch": payload.get("generated_epoch"),
        "not_applicable_reason": payload.get("not_applicable_reason"),
        "primary_reason": payload.get("primary_reason"),
        "latest_global_blocker": payload.get("latest_global_blocker"),
        "first_zero_stage": payload.get("first_zero_stage"),
        "phase2_starvation_reason": payload.get("phase2_starvation_reason"),
        "phase2_input_count": payload.get("phase2_input_count"),
        "phase2_input_candidate_count": payload.get("phase2_input_candidate_count"),
        "raw_candidate_count": payload.get("raw_candidate_count"),
        "feed_fresh": payload.get("feed_fresh"),
        "option_tick_fresh": payload.get("option_tick_fresh"),
        "by_symbol_keys": tuple(by_symbol.keys()),
    }
    if "last_candidate_funnel_by_symbol" in payload:
        summary["last_candidate_funnel_by_symbol"] = payload.get("last_candidate_funnel_by_symbol") or {}
    if "last_symbol_snapshot" in payload:
        summary["last_symbol_snapshot"] = _summarize_last_symbol_snapshot(payload.get("last_symbol_snapshot"))
    return {
        "path": str(path),
        "exists": True,
        "payload_summary": summary,
        "safety_flags": {
            "read_only": payload.get("read_only"),
            "is_order_action": payload.get("is_order_action"),
            "broker_api_called": payload.get("broker_api_called"),
            "append": payload.get("append"),
        },
    }


def _summarize_last_symbol_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    keys = (
        "symbol",
        "candidate_funnel_stage",
        "candidate_reason",
        "reject_reason",
        "final_emit_block_reason",
        "raw_candidate_count",
        "quote_health_state",
        "ltp_age_sec",
        "reject_gate_reasons",
        "scan_reject_counts",
    )
    return {key: value.get(key) for key in keys if key in value}


def _build_warnings(
    tick_integrity: Mapping[str, Any],
    replay_coverage: Mapping[str, Any],
    runtime_artifacts: Mapping[str, Any],
    wfa_proxy: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not tick_integrity.get("exists"):
        warnings.append("tick_file_missing")
    if tick_integrity.get("non_monotonic_ticks"):
        warnings.append("tick_file_has_non_monotonic_timestamps")
    missing_index_symbols = tuple(tick_integrity.get("missing_index_symbols") or ())
    if missing_index_symbols:
        warnings.append(f"tick_dataset_missing_index_symbols:{','.join(missing_index_symbols)}")
    missing_replay_keys = tuple(replay_coverage.get("missing_keys") or ())
    if missing_replay_keys:
        warnings.append(f"replay_missing_keys:{','.join(missing_replay_keys)}")
    if replay_coverage.get("production_equivalent") is False:
        warnings.append("replay_is_diagnostic_not_production_equivalent")
    if not runtime_artifacts.get("complete_per_symbol_table_available"):
        warnings.append("runtime_artifacts_do_not_have_complete_per_symbol_table")
    if wfa_proxy.get("proxy_only"):
        warnings.append("wfa_is_proxy_research_not_live_option_edge_proof")
    is_oos_counts = wfa_proxy.get("is_oos_counts") or {}
    if is_oos_counts and set(is_oos_counts) != {"True"}:
        warnings.append("wfa_is_oos_flags_are_not_all_true")
    return warnings


def _build_conclusions(
    tick_integrity: Mapping[str, Any],
    replay_coverage: Mapping[str, Any],
    runtime_artifacts: Mapping[str, Any],
    wfa_proxy: Mapping[str, Any],
) -> list[str]:
    conclusions = [
        "Do not loosen freshness, entropy, lifecycle, Phase 2, risk, broker, or kill-switch gates based on this evidence.",
        "Current evidence supports candidate starvation before Phase 2, not a proven independent failure of every named strategy.",
    ]
    if tick_integrity.get("structurally_usable"):
        conclusions.append("Tick file is structurally usable for symbols present in the dataset.")
    if replay_coverage.get("production_equivalent") is False:
        conclusions.append("A production-equivalent read-only replay harness is still required for promotion-quality analysis.")
    if wfa_proxy.get("total_pnl") is not None and (wfa_proxy.get("total_pnl") or 0) < 0:
        conclusions.append("Proxy WFA is negative after slippage and should be treated as a warning, not as edge proof.")
    return conclusions


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _tick_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row.get(key) for key in ("ts", "symbol", "ltp", "bid", "ask", "vol")}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _missing_summary(path: str | Path | None) -> dict[str, Any]:
    return {"path": str(path) if path is not None else None, "exists": False}
