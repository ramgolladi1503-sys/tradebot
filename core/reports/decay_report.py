from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ml.strategy_decay_predictor import generate_decay_report


def run_decay_report(output_path: str = "logs/decay_report.json") -> dict:
    report = generate_decay_report()
    report["generated_at"] = datetime.now().isoformat()
    Path(output_path).parent.mkdir(exist_ok=True)
    Path(output_path).write_text(json.dumps(report, indent=2))
    return report
