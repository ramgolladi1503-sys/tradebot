"""Migration note:
Fallback to build_decay_report when run_decay_report is not available.
This keeps daily_ops resilient across report API changes.
"""

from datetime import datetime
from pathlib import Path
import runpy
from core.paths import logs_dir

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from ml.decay_dataset import build_decay_dataset
from core.reports import decay_report as decay_report_module


def _build_decay_report():
    run_fn = getattr(decay_report_module, "run_decay_report", None)
    if callable(run_fn):
        return run_fn()

    build_fn = getattr(decay_report_module, "build_decay_report", None)
    if callable(build_fn):
        day = datetime.now().strftime("%Y-%m-%d")
        out_path = logs_dir() / f"decay_report_{day}.json"
        report_path = build_fn(day, out_path)
        return {"source": "build_decay_report", "path": str(report_path)}

    raise RuntimeError("No decay report builder available")


def main():
    build_decay_dataset()
    report = _build_decay_report()
    print(report)
    return report


if __name__ == "__main__":
    main()
