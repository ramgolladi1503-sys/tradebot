from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .schema import GateDecision, TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _default_outcomes_path(date_key: str) -> Path:
    base = str(getattr(cfg, "OUTCOME_REPLAY_DIR", "") or "").strip()
    if base:
        return Path(base) / f"{date_key}.jsonl"
    return repo_root() / "runtime" / "analytics" / "outcomes" / f"{date_key}.jsonl"


def _default_report_path(date_key: str) -> Path:
    base = str(getattr(cfg, "GATE_SCORECARD_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "gate_scorecard.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "gate_scorecard.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _iter_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    out.append(payload)
    except Exception:
        return []
    return out


def _normalize_outcome_row(payload: Mapping[str, Any]) -> dict | None:
    raw = dict(payload or {})
    candidate = raw.get("trade_outcome") if isinstance(raw.get("trade_outcome"), Mapping) else raw
    if not isinstance(candidate, Mapping):
        return None
    try:
        outcome = TradeOutcome.from_dict(dict(candidate))
    except Exception:
        return None
    event_ref_id = str(raw.get("event_ref_id") or raw.get("source_event_id") or "").strip() or None
    return {"trade_outcome": outcome, "event_ref_id": event_ref_id}


def load_outcome_replay_rows(date_key: str, outcome_paths: Iterable[Path] | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in list(outcome_paths or [_default_outcomes_path(date_key)]):
        for payload in _iter_jsonl(path):
            normalized = _normalize_outcome_row(payload)
            if normalized is not None:
                rows.append(normalized)
    rows.sort(key=lambda row: int(row["trade_outcome"].ts_epoch_ms))
    return rows


def _coerce_event(item: TradeIntentEvent | Mapping[str, Any]) -> tuple[TradeIntentEvent, dict] | None:
    if isinstance(item, TradeIntentEvent):
        return item, item.to_dict()
    if not isinstance(item, Mapping):
        return None
    raw = dict(item)
    try:
        event = TradeIntentEvent.from_dict(raw)
    except Exception:
        return None
    return event, raw


def _event_type(event: TradeIntentEvent, raw: Mapping[str, Any]) -> str:
    intent = str(event.intent or "").strip().lower()
    if intent in {"accepted", "rejected", "advisory"}:
        return intent
    status = str(raw.get("status") or "").strip().upper()
    reject_reason = str(raw.get("reject_reason") or raw.get("permission_reason") or "").strip()
    if reject_reason or status in {"REJECTED", "BLOCKED", "INVALIDATED", "EXPIRED"}:
        return "rejected"
    if status in {"ACTIVE", "FILLED", "EXECUTED", "RESOLVED"}:
        return "accepted"
    return "advisory"


def _normalize_gate_decisions(event: TradeIntentEvent, raw: Mapping[str, Any], event_kind: str) -> list[GateDecision]:
    out: list[GateDecision] = []
    for gd in list(event.gate_decisions or ()):  # type: ignore[arg-type]
        if isinstance(gd, GateDecision):
            out.append(gd)
    if out:
        return out

    raw_gates = raw.get("gate_decisions")
    if isinstance(raw_gates, list):
        for item in raw_gates:
            if not isinstance(item, Mapping):
                continue
            try:
                out.append(GateDecision.from_dict(item))
            except Exception:
                continue
    if out:
        return out

    # Fail-closed fallback: rejected events with unknown gate are still counted.
    if event_kind == "rejected":
        gate_name = str(raw.get("gate_name") or "unknown_gate").strip() or "unknown_gate"
        reason = str(event.reject_reason or raw.get("reject_reason") or "unknown_reject").strip() or "unknown_reject"
        out.append(GateDecision(gate_name=gate_name, passed=False, reason=reason, metrics_snapshot={}))
    return out


def _match_outcome(event: TradeIntentEvent, outcomes: Sequence[Mapping[str, Any]]) -> TradeOutcome | None:
    for row in outcomes:
        if str(row.get("event_ref_id") or "").strip() == event.event_id:
            out = row.get("trade_outcome")
            if isinstance(out, TradeOutcome):
                return out

    for row in outcomes:
        out = row.get("trade_outcome")
        if isinstance(out, TradeOutcome) and out.event_id == event.event_id:
            return out

    candidates: list[tuple[int, int, TradeOutcome]] = []
    for row in outcomes:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if out.trade_key != event.trade_key:
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(out.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        candidates.append((forward_bias, delta, out))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
    return None


def _outcome_bucket(outcome: TradeOutcome | None) -> str:
    label = str(getattr(outcome, "outcome", "") or "").strip().lower()
    if label == "hit_target":
        return "win"
    if label == "hit_sl":
        return "lose"
    return "neutral"


def _ratio(numer: int, denom: int) -> float | None:
    if int(denom) <= 0:
        return None
    return float(numer) / float(denom)


def build_gate_scorecard(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)

    if events is None:
        event_rows = load_trade_intent_events()
    else:
        event_rows = list(events)

    normalized_events: list[tuple[TradeIntentEvent, dict, str]] = []
    for row in event_rows:
        coerced = _coerce_event(row)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        normalized_events.append((event, raw, _event_type(event, raw)))

    if outcomes is None:
        normalized_outcomes = load_outcome_replay_rows(date_key, outcome_paths=outcome_paths)
    else:
        normalized_outcomes = []
        for row in outcomes:
            if isinstance(row, TradeOutcome):
                normalized_outcomes.append({"trade_outcome": row, "event_ref_id": None})
                continue
            if isinstance(row, Mapping):
                normalized = _normalize_outcome_row(row)
                if normalized is not None:
                    normalized_outcomes.append(normalized)

    per_gate_reason: dict[tuple[str, str], dict[str, Any]] = {}
    per_gate: dict[str, dict[str, int]] = {}

    for event, raw, kind in normalized_events:
        matched_outcome = _match_outcome(event, normalized_outcomes)
        outcome_bucket = _outcome_bucket(matched_outcome)
        gate_decisions = _normalize_gate_decisions(event, raw, kind)

        for gd in gate_decisions:
            gate_name = str(gd.gate_name or "unknown_gate").strip() or "unknown_gate"
            gate_stats = per_gate.setdefault(
                gate_name,
                {
                    "blocked_would_win": 0,
                    "blocked_would_lose": 0,
                    "blocked_neutral": 0,
                    "blocked_count": 0,
                    "pass_would_win": 0,
                    "pass_would_lose": 0,
                    "pass_neutral": 0,
                    "pass_count": 0,
                },
            )

            if kind == "rejected" and gd.passed is False:
                reject_reason = str(event.reject_reason or gd.reason or raw.get("reject_reason") or "unknown_reject").strip() or "unknown_reject"
                key = (gate_name, reject_reason)
                bucket = per_gate_reason.setdefault(
                    key,
                    {
                        "gate_name": gate_name,
                        "reject_reason": reject_reason,
                        "blocked_count": 0,
                        "blocked_would_win": 0,
                        "blocked_would_lose": 0,
                        "blocked_neutral": 0,
                    },
                )
                bucket["blocked_count"] += 1
                gate_stats["blocked_count"] += 1
                if outcome_bucket == "win":
                    bucket["blocked_would_win"] += 1
                    gate_stats["blocked_would_win"] += 1
                elif outcome_bucket == "lose":
                    bucket["blocked_would_lose"] += 1
                    gate_stats["blocked_would_lose"] += 1
                else:
                    bucket["blocked_neutral"] += 1
                    gate_stats["blocked_neutral"] += 1
                continue

            if kind == "accepted" and gd.passed is True:
                gate_stats["pass_count"] += 1
                if outcome_bucket == "win":
                    gate_stats["pass_would_win"] += 1
                elif outcome_bucket == "lose":
                    gate_stats["pass_would_lose"] += 1
                else:
                    gate_stats["pass_neutral"] += 1

    by_gate_reject_reason: list[dict] = []
    for (_gate, _reason), row in per_gate_reason.items():
        blocked_count = int(row["blocked_count"])
        win = int(row["blocked_would_win"])
        lose = int(row["blocked_would_lose"])
        by_gate_reject_reason.append(
            {
                "gate_name": row["gate_name"],
                "reject_reason": row["reject_reason"],
                "blocked_count": blocked_count,
                "blocked_would_win": win,
                "blocked_would_lose": lose,
                "blocked_neutral": int(row["blocked_neutral"]),
                "net_edge_score": ((float(win) - float(lose)) / float(blocked_count)) if blocked_count > 0 else 0.0,
            }
        )
    by_gate_reject_reason.sort(
        key=lambda row: (
            -(int(row.get("blocked_count") or 0)),
            str(row.get("gate_name") or ""),
            str(row.get("reject_reason") or ""),
        )
    )

    gate_precision_recall: list[dict] = []
    for gate_name, stats in sorted(per_gate.items(), key=lambda item: item[0]):
        blocked_count = int(stats["blocked_count"])
        pass_count = int(stats["pass_count"])
        blocked_would_lose = int(stats["blocked_would_lose"])
        blocked_would_win = int(stats["blocked_would_win"])
        pass_would_lose = int(stats["pass_would_lose"])
        pass_would_win = int(stats["pass_would_win"])

        gate_precision_recall.append(
            {
                "gate_name": gate_name,
                "blocked_count": blocked_count,
                "pass_count": pass_count,
                "blocked_would_lose": blocked_would_lose,
                "blocked_would_win": blocked_would_win,
                "blocked_neutral": int(stats["blocked_neutral"]),
                "pass_would_lose": pass_would_lose,
                "pass_would_win": pass_would_win,
                "pass_neutral": int(stats["pass_neutral"]),
                "block_precision": _ratio(blocked_would_lose, blocked_count),
                "block_recall": _ratio(blocked_would_lose, blocked_would_lose + pass_would_lose),
                "allow_precision": _ratio(pass_would_win, pass_count),
                "allow_recall": _ratio(pass_would_win, pass_would_win + blocked_would_win),
            }
        )

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "total_events": len(normalized_events),
        "total_rejected_events": sum(int(row.get("blocked_count") or 0) for row in by_gate_reject_reason),
        "total_accepted_gate_pass_events": sum(int(row.get("pass_count") or 0) for row in gate_precision_recall),
        "by_gate_reject_reason": by_gate_reject_reason,
        "gate_precision_recall": gate_precision_recall,
    }

    path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(path, report)
    report["output_path"] = str(path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build gate effectiveness scorecard from event outcomes.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange day).")
    parser.add_argument(
        "--outcomes-path",
        action="append",
        default=None,
        help="Optional replay outcomes JSONL path (repeatable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    paths = [Path(p) for p in (args.outcomes_path or [])] if args.outcomes_path else None
    result = build_gate_scorecard(args.date, outcome_paths=paths)
    print(
        json.dumps(
            {
                "date": result.get("date"),
                "total_events": result.get("total_events"),
                "total_rejected_events": result.get("total_rejected_events"),
                "output_path": result.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
