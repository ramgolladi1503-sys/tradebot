from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _pick_latest(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _top(counter: Counter[str], limit: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(limit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze candidate lineage JSONL artifacts.")
    parser.add_argument("--lineage", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args()

    lineage = args.lineage or _pick_latest(sorted(Path("runtime/candidate_lineage").glob("candidate_funnel_*.jsonl")))
    summary = args.summary or _pick_latest(sorted(Path("runtime/candidate_lineage").glob("candidate_funnel_summary_*.jsonl")))

    lineage_rows = _read_jsonl(lineage) if lineage else []
    summary_rows = _read_jsonl(summary) if summary else []
    cycles = len({row.get("cycle_id") for row in summary_rows if row.get("cycle_id")})

    generated_total = sum(int(row.get("generated_total") or 0) for row in summary_rows)
    tradebuilder_input_total = sum(int(row.get("tradebuilder_input_total") or 0) for row in summary_rows)
    phase2_input_total = sum(int(row.get("phase2_input_total") or 0) for row in summary_rows)
    rankable_total = sum(int(row.get("rankable_total") or 0) for row in summary_rows)
    executable_total = sum(int(row.get("executable_total") or 0) for row in summary_rows)
    top_opportunity_total = sum(int(row.get("top_opportunity_total") or 0) for row in summary_rows)

    block_counter: Counter[str] = Counter()
    strategy_generated: Counter[str] = Counter()
    strategy_blocked: Counter[str] = Counter()
    strategy_executable: Counter[str] = Counter()
    warnings: list[str] = []

    for row in lineage_rows:
        strategy = str(row.get("strategy_name") or row.get("strategy_id") or "unknown").strip() or "unknown"
        strategy_generated[strategy] += 1
        block_reason = str(row.get("block_reason") or "").strip()
        block_reason_code = str(row.get("block_reason_code") or "").strip()
        if block_reason:
            block_counter[block_reason] += 1
        if block_reason_code and block_reason_code != block_reason:
            block_counter[block_reason_code] += 1
        for reason in row.get("downgrade_reasons") or []:
            reason = str(reason).strip()
            if reason:
                block_counter[reason] += 1
        if str(row.get("stage_status") or "").strip().lower() == "blocked":
            strategy_blocked[strategy] += 1
        if bool(row.get("executable")):
            strategy_executable[strategy] += 1
        if str(row.get("stage_status") or "").strip().lower() != "blocked" and block_reason:
            warnings.append(f"selected-or-passed row has block_reason: {row.get('candidate_id')}")
        if bool(row.get("top_opportunity")) and not bool(row.get("executable")):
            warnings.append(f"top_opportunity not executable: {row.get('candidate_id')}")
        if any(bool(row.get(flag)) for flag in ("fallback_used", "recovered_fallback", "stale_quote", "advisory", "degraded")) and bool(row.get("executable")):
            warnings.append(f"degraded row executable: {row.get('candidate_id')}")
        if phase2_input_total > tradebuilder_input_total and not str(row.get("entry_path") or "").strip():
            warnings.append("phase2_input_total exceeds tradebuilder_input_total without explicit entry_path")

    print(f"cycles analyzed: {cycles}")
    print(f"generated_total: {generated_total}")
    print(f"tradebuilder_input_total: {tradebuilder_input_total}")
    print(f"phase2_input_total: {phase2_input_total}")
    print(f"rankable_total: {rankable_total}")
    print(f"executable_total: {executable_total}")
    print(f"top_opportunity_total: {top_opportunity_total}")
    print("top 10 block reasons:")
    for reason, count in _top(block_counter, 10):
        print(f"  {reason}: {count}")
    print("top 10 strategies by generated count:")
    for strategy, count in _top(strategy_generated, 10):
        print(f"  {strategy}: {count}")
    print("top 10 strategies by blocked count:")
    for strategy, count in _top(strategy_blocked, 10):
        print(f"  {strategy}: {count}")
    print("top 10 strategies by executable count:")
    for strategy, count in _top(strategy_executable, 10):
        print(f"  {strategy}: {count}")
    for warning in dict.fromkeys(warnings):
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
