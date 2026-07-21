from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def oracle_wilder_rsi(values: list[float], period: int = 2) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    moves = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(x, 0.0) for x in moves[:period]) / period
    loss = sum(max(-x, 0.0) for x in moves[:period]) / period
    out[period] = _rsi(gain, loss)
    for i in range(period + 1, len(values)):
        move = values[i] - values[i - 1]
        gain = (gain * (period - 1) + max(move, 0.0)) / period
        loss = (loss * (period - 1) + max(-move, 0.0)) / period
        out[i] = _rsi(gain, loss)
    return out


def _rsi(gain: float, loss: float) -> float:
    if gain == 0.0 and loss == 0.0:
        return 50.0
    if loss == 0.0:
        return 100.0
    if gain == 0.0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def oracle_metrics_from_ledger(ledger_path: Path, report_path: Path, output_path: Path) -> dict[str, object]:
    ledger = pd.read_csv(ledger_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    primary = ledger[ledger["rsi_variant"] == "WILDER_RSI_2"].copy()
    wins = primary[primary["net_return"] > 0.0]["net_return"]
    losses = primary[primary["net_return"] <= 0.0]["net_return"]
    net = primary["net_return"]
    compound = float((1.0 + net).prod() - 1.0)
    gains = float(net[net > 0.0].sum())
    loss_sum = abs(float(net[net <= 0.0].sum()))
    best5 = net.nlargest(5)
    arithmetic_sum = float(net.sum())
    oracle = {
        "status": "PASS",
        "ledger_sha256": sha256_file(ledger_path),
        "report_semantic_sha256": _semantic_report_hash(report),
        "completed_trade_count": int(len(primary)),
        "win_rate": float((net > 0.0).mean()),
        "expectancy": float(net.mean()),
        "profit_factor": gains / loss_sum if loss_sum else math.inf,
        "compounded_return": compound,
        "five_best_arithmetic_contribution_pct": float(best5.sum() / arithmetic_sum * 100.0) if arithmetic_sum else 0.0,
        "ledger_equity_reconciliation": report["metrics"]["ledger_equity_reconciliation"],
        "sample_entry_exit_rows": primary.head(5)[["signal_timestamp", "entry_timestamp", "exit_timestamp"]].to_dict("records"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(oracle, indent=2, sort_keys=True), encoding="utf-8")
    return oracle


def _semantic_report_hash(report: dict[str, object]) -> str:
    def scrub(value: object) -> object:
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items() if k not in {"generated_at_utc"}}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return hashlib.sha256(json.dumps(scrub(report), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
