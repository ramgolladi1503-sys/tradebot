from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.candidate_outcome_tracker import candidate_outcome_tracker_path
from core.candidate_outcome_truth import NOT_EXECUTABLE, STOP_HIT, TARGET_HIT, TIMEOUT
from core.expectancy.setup_fingerprint import build_setup_fingerprint
from core.paths import runtime_dir


STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION = 1
_DEFAULT_EXPECTANCY_SUBDIR = "expectancy"
_DEFAULT_EXPECTANCY_FILENAME_JSON = "strategy_regime_expectancy_latest.json"
_DEFAULT_EXPECTANCY_FILENAME_MD = "strategy_regime_expectancy_latest.md"

_EXECUTABLE_OUTCOME_STATUSES = {TARGET_HIT, STOP_HIT, TIMEOUT}
_BLOCKED_OUTCOME_STATUSES = {"INVALID_INPUT", "NO_OBSERVATIONS", "AMBIGUOUS_SAME_BAR"}
_POSITIVE_KEEP_THRESHOLD = 0.15
_POSITIVE_KEEP_SAMPLE_SIZE = 50
_MIN_SAMPLE_SIZE = 30


@dataclass(frozen=True)
class StrategyRegimeExpectancyGroup:
    schema_version: int
    group_key: str
    strategy_family: str
    regime: str
    index: str
    expiry_type: str
    option_type: str
    direction: str
    sample_count: int
    executable_count: int
    not_executable_count: int
    win_count: int
    loss_count: int
    timeout_count: int
    target_hit_count: int
    stop_hit_count: int
    win_rate: float
    avg_gross_r: float
    avg_cost_adjusted_r: float
    median_cost_adjusted_r: float
    total_cost_adjusted_r: float
    target_hit_rate: float
    stop_hit_rate: float
    timeout_rate: float
    max_drawdown_r: float
    fallback_excluded_count: int
    blocked_excluded_count: int
    keep_watch_kill_status: str
    status_reason: str
    read_only: bool = True
    append: bool = False

    @property
    def safety(self) -> dict[str, object]:
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safety"] = dict(self.safety)
        return payload


@dataclass(frozen=True)
class StrategyRegimeExpectancyReport:
    schema_version: int
    generated_by: str
    source: str
    candidate_outcome_count: int
    group_count: int
    groups: tuple[StrategyRegimeExpectancyGroup, ...]
    read_only: bool = True
    append: bool = False

    @property
    def safety(self) -> dict[str, object]:
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["groups"] = [group.to_payload() for group in self.groups]
        payload["safety"] = dict(self.safety)
        return payload


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any, *, default: str = "unknown") -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return text or default


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:  # NaN guard.
        return None
    return number


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _group_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        _slug(row.get("strategy_family")),
        _slug(row.get("regime")),
        _slug(row.get("index")),
        _slug(row.get("expiry_type")),
        _slug(row.get("option_type")),
        _slug(row.get("direction")),
    )


def _group_key_label(parts: tuple[str, str, str, str, str, str]) -> str:
    return "|".join(parts)


def _setup_group_key(row: Mapping[str, Any]) -> tuple[str]:
    setup_id = _text(row.get("setup_id"))
    if setup_id:
        return (setup_id,)
    return (build_setup_fingerprint(row).setup_id,)


def _setup_group_key_label(parts: tuple[str]) -> str:
    return parts[0]


def _sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    signal_epoch = _float(row.get("signal_epoch"))
    candidate_id = _text(row.get("candidate_id"))
    trade_id = _text(row.get("trade_id"))
    outcome_status = _text(row.get("outcome_status"))
    window_sec = int(_float(row.get("window_sec")) or 0)
    return (
        signal_epoch if signal_epoch is not None else float("inf"),
        candidate_id,
        trade_id,
        outcome_status,
        window_sec,
        _text(row.get("symbol")),
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def load_candidate_outcomes(source: str | Path | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_dir():
            candidate_path = path / "candidate_outcomes.jsonl"
            if candidate_path.exists():
                return _load_jsonl(candidate_path)
            return []
        if path.suffix.lower() == ".jsonl":
            return _load_jsonl(path)
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [dict(row) for row in payload if isinstance(row, Mapping)]
            if isinstance(payload, Mapping):
                rows = payload.get("rows") or payload.get("outcomes") or payload.get("results") or []
                if isinstance(rows, list):
                    return [dict(row) for row in rows if isinstance(row, Mapping)]
            return []
        raise ValueError(f"unsupported candidate outcome source: {path}")
    return [dict(row) for row in source if isinstance(row, Mapping)]


def _is_fallback(row: Mapping[str, Any]) -> bool:
    return _bool(row.get("fallback_used"))


def _is_executable_outcome(row: Mapping[str, Any]) -> bool:
    if _is_fallback(row):
        return False
    return _text(row.get("outcome_status")) in _EXECUTABLE_OUTCOME_STATUSES


def _count_rows(rows: list[Mapping[str, Any]], *, predicate) -> int:
    return sum(1 for row in rows if predicate(row))


def _drawdown(cost_adjusted_series: list[float]) -> float:
    if not cost_adjusted_series:
        return 0.0
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in cost_adjusted_series:
        equity += float(value)
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return round(max_drawdown, 6)


def _status_for_group(sample_count: int, avg_cost_adjusted_r: float) -> tuple[str, str]:
    if sample_count < _MIN_SAMPLE_SIZE:
        return "INSUFFICIENT_DATA", "sample_count_below_threshold"
    if avg_cost_adjusted_r <= 0:
        return "KILL", "avg_cost_adjusted_r_non_positive"
    if sample_count >= _POSITIVE_KEEP_SAMPLE_SIZE and avg_cost_adjusted_r >= _POSITIVE_KEEP_THRESHOLD:
        return "KEEP", "strong_positive_expectancy_and_sample_threshold_met"
    return "WATCH", "positive_expectancy_but_keep_threshold_not_met"


def _group_rows(
    rows: list[dict[str, Any]],
    *,
    group_by_setup_id: bool = False,
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = _setup_group_key(row) if group_by_setup_id else _group_key(row)
        grouped.setdefault(key, []).append(row)
    for key, group_rows in grouped.items():
        group_rows.sort(key=_sort_key)
    return grouped


def _numeric_values(rows: list[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _float(row.get(key))
        if value is None:
            continue
        values.append(float(value))
    return values


def _group_metrics(key: tuple[str, ...], rows: list[dict[str, Any]]) -> StrategyRegimeExpectancyGroup:
    if len(key) == 1:
        first_row = rows[0] if rows else {}
        group_key = _setup_group_key_label((str(key[0]),))
        strategy_family = _slug(first_row.get("strategy_family"))
        regime = _slug(first_row.get("regime"))
        index = _slug(first_row.get("index"))
        expiry_type = _slug(first_row.get("expiry_type"))
        option_type = _slug(first_row.get("option_type"))
        direction = _slug(first_row.get("direction"))
    else:
        group_key = _group_key_label(key)  # type: ignore[arg-type]
        strategy_family, regime, index, expiry_type, option_type, direction = key  # type: ignore[misc]
    sample_count = len(rows)
    fallback_excluded_count = _count_rows(rows, predicate=_is_fallback)
    executable_rows = [row for row in rows if _is_executable_outcome(row)]
    not_executable_rows = [
        row
        for row in rows
        if not _is_fallback(row) and _text(row.get("outcome_status")) == NOT_EXECUTABLE
    ]
    blocked_rows = [
        row
        for row in rows
        if not _is_fallback(row)
        and _text(row.get("outcome_status")) not in _EXECUTABLE_OUTCOME_STATUSES
        and _text(row.get("outcome_status")) != NOT_EXECUTABLE
    ]

    exec_count = len(executable_rows)
    target_hit_count = _count_rows(executable_rows, predicate=lambda row: _text(row.get("outcome_status")) == TARGET_HIT)
    stop_hit_count = _count_rows(executable_rows, predicate=lambda row: _text(row.get("outcome_status")) == STOP_HIT)
    timeout_count = _count_rows(executable_rows, predicate=lambda row: _text(row.get("outcome_status")) == TIMEOUT)
    win_count = target_hit_count
    loss_count = stop_hit_count
    gross_values = _numeric_values(executable_rows, "gross_r")
    cost_values = _numeric_values(executable_rows, "cost_adjusted_r")
    avg_gross_r = round(sum(gross_values) / len(gross_values), 6) if gross_values else 0.0
    avg_cost_adjusted_r = round(sum(cost_values) / len(cost_values), 6) if cost_values else 0.0
    median_cost_adjusted_r = round(float(statistics.median(cost_values)), 6) if cost_values else 0.0
    total_cost_adjusted_r = round(sum(cost_values), 6) if cost_values else 0.0
    win_rate = round(win_count / exec_count, 6) if exec_count else 0.0
    target_hit_rate = round(target_hit_count / exec_count, 6) if exec_count else 0.0
    stop_hit_rate = round(stop_hit_count / exec_count, 6) if exec_count else 0.0
    timeout_rate = round(timeout_count / exec_count, 6) if exec_count else 0.0
    max_drawdown_r = _drawdown(cost_values)
    keep_watch_kill_status, status_reason = _status_for_group(sample_count, avg_cost_adjusted_r)
    return StrategyRegimeExpectancyGroup(
        schema_version=STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION,
        group_key=group_key,
        strategy_family=strategy_family,
        regime=regime,
        index=index,
        expiry_type=expiry_type,
        option_type=option_type,
        direction=direction,
        sample_count=sample_count,
        executable_count=exec_count,
        not_executable_count=len(not_executable_rows),
        win_count=win_count,
        loss_count=loss_count,
        timeout_count=timeout_count,
        target_hit_count=target_hit_count,
        stop_hit_count=stop_hit_count,
        win_rate=win_rate,
        avg_gross_r=avg_gross_r,
        avg_cost_adjusted_r=avg_cost_adjusted_r,
        median_cost_adjusted_r=median_cost_adjusted_r,
        total_cost_adjusted_r=total_cost_adjusted_r,
        target_hit_rate=target_hit_rate,
        stop_hit_rate=stop_hit_rate,
        timeout_rate=timeout_rate,
        max_drawdown_r=max_drawdown_r,
        fallback_excluded_count=fallback_excluded_count,
        blocked_excluded_count=len(blocked_rows),
        keep_watch_kill_status=keep_watch_kill_status,
        status_reason=status_reason,
    )


def aggregate_strategy_regime_expectancy(
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]],
    *,
    group_by_setup_id: bool = False,
) -> StrategyRegimeExpectancyReport:
    rows = load_candidate_outcomes(candidate_outcomes)
    grouped_rows = _group_rows(rows, group_by_setup_id=group_by_setup_id)
    groups = tuple(
        _group_metrics(key, grouped_rows[key])
        for key in sorted(grouped_rows.keys())
    )
    source = str(candidate_outcome_tracker_path()) if isinstance(candidate_outcomes, (str, Path)) else "in_memory"
    return StrategyRegimeExpectancyReport(
        schema_version=STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION,
        generated_by="strategy_regime_expectancy_aggregator",
        source=source,
        candidate_outcome_count=len(rows),
        group_count=len(groups),
        groups=groups,
    )


def _markdown_table(rows: tuple[StrategyRegimeExpectancyGroup, ...]) -> str:
    headers = [
        "group_key",
        "sample_count",
        "executable_count",
        "not_executable_count",
        "win_count",
        "loss_count",
        "timeout_count",
        "avg_cost_adjusted_r",
        "median_cost_adjusted_r",
        "max_drawdown_r",
        "keep_watch_kill_status",
        "status_reason",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        payload = row.to_payload()
        lines.append("| " + " | ".join(str(payload.get(column, "")) for column in headers) + " |")
    return "\n".join(lines)


def write_strategy_regime_expectancy_report(
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]],
    output_dir: str | Path | None = None,
    *,
    group_by_setup_id: bool = False,
) -> tuple[Path, Path, StrategyRegimeExpectancyReport]:
    report = aggregate_strategy_regime_expectancy(candidate_outcomes, group_by_setup_id=group_by_setup_id)
    root = Path(output_dir).expanduser() if output_dir is not None else runtime_dir() / _DEFAULT_EXPECTANCY_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / _DEFAULT_EXPECTANCY_FILENAME_JSON
    md_path = root / _DEFAULT_EXPECTANCY_FILENAME_MD
    json_payload = report.to_payload()
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_lines = [
        "# Strategy-Regime Expectancy Report",
        "",
        f"- Schema version: {report.schema_version}",
        f"- Generated by: {report.generated_by}",
        f"- Source: {report.source}",
        f"- Candidate outcome count: {report.candidate_outcome_count}",
        f"- Group count: {report.group_count}",
        "",
        "## Safety",
    ]
    for key, value in report.safety.items():
        markdown_lines.append(f"- {key}: {value}")
    markdown_lines.extend(
        [
            "",
            "## Keep / Watch / Kill",
        ]
    )
    for group in report.groups:
        markdown_lines.append(
            f"- {group.group_key}: {group.keep_watch_kill_status} ({group.status_reason}) "
            f"sample_count={group.sample_count} avg_cost_adjusted_r={group.avg_cost_adjusted_r}"
        )
    markdown_lines.extend(
        [
            "",
            "## Group Metrics",
            "",
            _markdown_table(report.groups),
            "",
            "This report does not prove strategy edge or runtime readiness.",
        ]
    )
    md_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    return json_path, md_path, report


def write_strategy_regime_expectancy_reports(
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]],
    output_dir: str | Path | None = None,
    *,
    group_by_setup_id: bool = False,
) -> tuple[Path, Path]:
    json_path, md_path, _ = write_strategy_regime_expectancy_report(
        candidate_outcomes,
        output_dir=output_dir,
        group_by_setup_id=group_by_setup_id,
    )
    return json_path, md_path


__all__ = [
    "STRATEGY_REGIME_EXPECTANCY_SCHEMA_VERSION",
    "StrategyRegimeExpectancyGroup",
    "StrategyRegimeExpectancyReport",
    "aggregate_strategy_regime_expectancy",
    "load_candidate_outcomes",
    "write_strategy_regime_expectancy_report",
    "write_strategy_regime_expectancy_reports",
]
