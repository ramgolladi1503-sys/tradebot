from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.code_excellence.unified_agent_elite_report import (
    AgentEliteSignal,
    build_unified_agent_elite_report,
    render_markdown,
    signal_from_mapping,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified Agent Elite report")
    parser.add_argument("--signals-json", default=None, help="Optional JSON file containing a list of agent signal objects")
    parser.add_argument("--out", required=True, help="Markdown report output path")
    args = parser.parse_args()

    signals = _load_signals(args.signals_json)
    report = build_unified_agent_elite_report(signals)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(report), encoding="utf-8")
    return 1 if report.verdict == "FAIL" else 0


def _load_signals(path: str | None) -> tuple[AgentEliteSignal, ...]:
    if not path:
        return ()
    source = Path(path)
    if not source.exists():
        return ()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("agents", [])
    if not isinstance(payload, list):
        return ()
    return tuple(signal_from_mapping(item) for item in payload if isinstance(item, dict))


if __name__ == "__main__":
    raise SystemExit(main())
