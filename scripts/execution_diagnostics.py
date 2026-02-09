import json
from pathlib import Path
from config import config as cfg
from core.fill_quality import get_latest_exec_quality


def _load(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def main():
    exec_analytics = _load("logs/execution_analytics.json") or {}
    fill_daily = _load("logs/fill_quality_daily.json") or {}
    latest_exec_q = get_latest_exec_quality()
    print("Execution diagnostics:")
    print(f"- slippage_bps (config): {getattr(cfg, 'SLIPPAGE_BPS', None)}")
    print(f"- avg_exec_quality (latest): {latest_exec_q}")
    if exec_analytics:
        print(f"- fill_ratio: {exec_analytics.get('fill_ratio')}")
        print(f"- avg_latency_ms: {exec_analytics.get('avg_latency_ms')}")
        print(f"- avg_slippage: {exec_analytics.get('avg_slippage')}")
    if fill_daily:
        latest_day = sorted(fill_daily.keys())[-1]
        print(f"- fill_quality_day: {latest_day}")
        print(f"- fill_rate: {fill_daily[latest_day].get('fill_rate')}")
        print(f"- avg_time_to_fill: {fill_daily[latest_day].get('avg_time_to_fill')}")
        print(f"- avg_slippage_vs_mid: {fill_daily[latest_day].get('avg_slippage_vs_mid')}")


if __name__ == "__main__":
    main()
