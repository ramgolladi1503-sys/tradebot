import json
from pathlib import Path


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def generate_hypotheses() -> list[dict]:
    decay = _load_json(Path("logs/decay_report.json"))
    exec_report = _load_json(Path("logs/execution_report.json"))
    if not decay and not exec_report:
        return [{"title": "insufficient_data", "trigger": "missing_reports", "expected": "run daily reports"}]

    hypotheses: list[dict] = []
    if decay:
        decaying = decay.get("decaying", []) or []
        if decaying:
            hypotheses.append(
                {
                    "title": "strategy_decay",
                    "trigger": "decay_report",
                    "suspected": "edge degradation",
                    "proposed": "reduce size and review signals",
                    "required_data": "decision_events + outcomes",
                    "expected": "stability improves after adjustment",
                }
            )
    if exec_report:
        fill_rate = exec_report.get("fill_rate")
        if fill_rate is not None and float(fill_rate) < 0.5:
            hypotheses.append(
                {
                    "title": "execution_quality",
                    "trigger": "low_fill_rate",
                    "suspected": "spread or stale quotes",
                    "proposed": "tighten quote freshness or reduce chase",
                    "required_data": "fill_quality + quotes",
                    "expected": "fill rate recovers",
                }
            )

    if not hypotheses:
        hypotheses.append({"title": "no_action", "trigger": "no_anomalies", "expected": "monitor"})
    return hypotheses


def write_hypotheses(path: Path):
    payload = {"hypotheses": generate_hypotheses()}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path
