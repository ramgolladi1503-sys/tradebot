import json
import time
from pathlib import Path


FILL_LOG_PATH = Path("logs/fill_quality.jsonl")
FILL_DAILY_PATH = Path("logs/fill_quality_daily.json")


def _load_daily():
    if not FILL_DAILY_PATH.exists():
        return {}
    try:
        return json.loads(FILL_DAILY_PATH.read_text())
    except Exception:
        return {}


def _save_daily(data):
    try:
        FILL_DAILY_PATH.parent.mkdir(exist_ok=True)
        FILL_DAILY_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def get_latest_exec_quality():
    data = _load_daily()
    if not data:
        return None
    try:
        day = sorted(data.keys())[-1]
        return data.get(day, {}).get("avg_exec_quality")
    except Exception:
        return None


def log_fill_quality(payload):
    try:
        FILL_LOG_PATH.parent.mkdir(exist_ok=True)
        with open(FILL_LOG_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        return
    _update_daily_summary(payload)


def _update_daily_summary(payload):
    day = time.strftime("%Y-%m-%d")
    data = _load_daily()
    row = data.get(day, {
        "attempts": 0,
        "fills": 0,
        "avg_time_to_fill": 0.0,
        "avg_slippage_vs_mid": 0.0,
        "avg_spread": 0.0,
        "avg_exec_quality": 0.0,
        "avg_shortfall": 0.0,
        "avg_opportunity_cost": 0.0,
        "avg_alpha_decay": 0.0,
        "avg_adverse_selection": 0.0,
    })

    row["attempts"] += 1
    decision_spread = payload.get("decision_spread")
    if decision_spread is not None:
        row["avg_spread"] = _running_avg(row["avg_spread"], decision_spread, row["attempts"])

    if payload.get("fill_price") is not None:
        row["fills"] += 1
        if payload.get("time_to_fill") is not None:
            row["avg_time_to_fill"] = _running_avg(
                row["avg_time_to_fill"], payload.get("time_to_fill"), row["fills"]
            )
        if payload.get("slippage_vs_mid") is not None:
            row["avg_slippage_vs_mid"] = _running_avg(
                row["avg_slippage_vs_mid"], payload.get("slippage_vs_mid"), row["fills"]
            )
        if payload.get("execution_quality_score") is not None:
            row["avg_exec_quality"] = _running_avg(
                row["avg_exec_quality"], payload.get("execution_quality_score"), row["fills"]
            )
        if payload.get("implementation_shortfall") is not None:
            row["avg_shortfall"] = _running_avg(
                row["avg_shortfall"], payload.get("implementation_shortfall"), row["fills"]
            )
        if payload.get("alpha_decay") is not None:
            row["avg_alpha_decay"] = _running_avg(
                row["avg_alpha_decay"], payload.get("alpha_decay"), row["fills"]
            )
        if payload.get("adverse_selection") is not None:
            row["avg_adverse_selection"] = _running_avg(
                row["avg_adverse_selection"], payload.get("adverse_selection"), row["fills"]
            )

    if payload.get("opportunity_cost") is not None:
        row["avg_opportunity_cost"] = _running_avg(
            row["avg_opportunity_cost"], payload.get("opportunity_cost"), row["attempts"]
        )

    row["fill_rate"] = round(row["fills"] / max(row["attempts"], 1), 4)
    data[day] = row
    _save_daily(data)


def _running_avg(prev_avg, new_val, n):
    try:
        return round(((prev_avg * (n - 1)) + new_val) / n, 6)
    except Exception:
        return prev_avg
