#!/usr/bin/env python3
"""Real 18-vector mutation campaign for the primitive PR #905 verifier."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _run_verifier(evidence_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_pr905_implementation.py"),
            "--evidence-root",
            str(evidence_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def _mutate_json(path: Path, fn) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mutate_jsonl(path: Path, fn) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fn(rows)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_mutation_campaign(evidence_root: Path) -> dict[str, Any]:
    baseline = _run_verifier(evidence_root)
    if baseline.returncode != 0:
        raise RuntimeError(f"BASELINE_VERIFIER_FAILED\n{baseline.stdout}\n{baseline.stderr}")

    orch = REPO_ROOT / "core" / "orchestrator.py"
    consumer = REPO_ROOT / "core" / "read_only_consumer_cycle.py"
    hook = REPO_ROOT / "core" / "trade_truth" / "truth_feed_runtime_hook.py"
    authority = REPO_ROOT / "core" / "runtime_authority_contract.py"

    pulse1 = evidence_root / "CHECKPOINT_PULSE_RUN1.jsonl"
    captured = evidence_root / "TRADEBUILDER_CAPTURED_CALLS.json"
    broker = evidence_root / "BROKER_WRITE_AUDIT.json"
    ledger = evidence_root / "CANONICAL_RUNTIME_CALL_LEDGER.json"

    mutations = [
        {
            "id": "M1",
            "name": "raw market_data bypass restored",
            "path": orch,
            "apply": lambda text: text + "\n# MUTANT M1\nbuilder_input = market_data\n",
        },
        {
            "id": "M2",
            "name": "synthetic runtime lineage default restored",
            "path": orch,
            "apply": lambda text: text + '\n# MUTANT M2\nreal_cycle_id = real_cycle_id or "live_cycle"\n',
        },
        {
            "id": "M3",
            "name": "candidate entry becomes TradeBuilder market price",
            "path": consumer,
            "apply": lambda text: text.replace(
                'spot_px = float(sym_snapshot.get("spot") or sym_snapshot.get("ltp"))',
                'spot_px = float(valid_candidates[0].get("entry") or 0.0)',
                1,
            ),
        },
        {
            "id": "M4",
            "name": "causal cutoff used as missing event timestamp fallback",
            "path": consumer,
            "apply": lambda text: text.replace(
                'event_ts = sym_snapshot.get("timestamp") or sym_snapshot.get("quote_timestamp")',
                'event_ts = sym_snapshot.get("timestamp") or sym_snapshot.get("quote_timestamp") or causal_cutoff_str',
                1,
            ),
        },
        {
            "id": "M5",
            "name": "CheckpointSpan span_id removed",
            "path": hook,
            "apply": lambda text: text.replace("    span_id: str\n", "    # span_id removed by mutant\n", 1),
        },
        {
            "id": "M6",
            "name": "TradeBuilder parent replaced with bare stage literal",
            "path": pulse1,
            "jsonl": lambda rows: [
                row.update({"parent_span_id": "CANDIDATE_POOL"})
                for row in rows
                if row.get("stage_name") == "TRADE_BUILDER"
            ],
        },
        {
            "id": "M7",
            "name": "emitted candidate-pool parent span removed",
            "path": pulse1,
            "jsonl": lambda rows: rows.__setitem__(
                slice(None),
                [row for row in rows if row.get("stage_name") != "CANDIDATE_POOL"],
            ),
        },
        {
            "id": "M8",
            "name": "TradeBuilder trace changed to foreign trace",
            "path": pulse1,
            "jsonl": lambda rows: [
                row.update({"trace_id": "foreign-trace"})
                for row in rows
                if row.get("stage_name") == "TRADE_BUILDER"
            ],
        },
        {
            "id": "M9",
            "name": "TradeBuilder call removed from observer",
            "path": consumer,
            "apply": lambda text: text.replace(
                "trade, trace = trade_builder.build_with_trace(",
                "trade, trace = removed_tradebuilder_call(",
                1,
            ),
        },
        {
            "id": "M10",
            "name": "TradeBuilder checkpoint removed from raw pulse",
            "path": pulse1,
            "jsonl": lambda rows: rows.__setitem__(
                slice(None),
                [row for row in rows if row.get("stage_name") != "TRADE_BUILDER"],
            ),
        },
        {
            "id": "M11",
            "name": "TradeBuilder checkpoint output hash corrupted",
            "path": pulse1,
            "jsonl": lambda rows: [
                row.update({"output_hash": "0" * 64})
                for row in rows
                if row.get("stage_name") == "TRADE_BUILDER"
            ],
        },
        {
            "id": "M12",
            "name": "captured exact TradeBuilder input price altered",
            "path": captured,
            "json": lambda data: [
                call["input"].update({"ltp": 11111.0})
                for call in data.get("calls", [])
                if call.get("run") == "run1"
            ],
        },
        {
            "id": "M13",
            "name": "unobserved synthetic stage inserted into ledger",
            "path": ledger,
            "json": lambda data: data.setdefault("observed_stages", []).append(
                {
                    "stage_name": "FAKE_SYNTHETIC_STAGE",
                    "span_id": "fake",
                    "trace_id": data.get("cycle_id"),
                    "parent_span_id": None,
                    "input_hash": "0" * 64,
                    "output_hash": "0" * 64,
                    "status": "PASS",
                }
            ),
        },
        {
            "id": "M14",
            "name": "UI ranked candidates made causal to TradeBuilder",
            "path": consumer,
            "apply": lambda text: text.replace(
                "    for c in valid_candidates:\n        sym = str(c.get(\"underlying\") or c.get(\"symbol\") or \"\").strip().upper()",
                "    ranked_candidates = list(valid_candidates)\n    for c in ranked_candidates:\n        sym = str(c.get(\"underlying\") or c.get(\"symbol\") or \"\").strip().upper()",
                1,
            ),
        },
        {
            "id": "M15",
            "name": "second candidate-selection authority introduced",
            "path": authority,
            "apply": lambda text: text.replace(
                '    RuntimeAuthorityStage(\n        40,\n        "legacy_opportunity_selection",',
                '    RuntimeAuthorityStage(\n        39,\n        "duplicate_selection",\n        "core.observer",\n        "select_best",\n        AuthorityKind.CANDIDATE_SELECTION,\n        False,\n        False,\n        "mutant",\n    ),\n    RuntimeAuthorityStage(\n        40,\n        "legacy_opportunity_selection",',
                1,
            ),
        },
        {
            "id": "M16",
            "name": "broker write primitive count made non-zero",
            "path": broker,
            "json": lambda data: next(iter(data.setdefault("call_counts", {})), None)
            and data["call_counts"].__setitem__(next(iter(data["call_counts"])), 1),
        },
        {
            "id": "M17",
            "name": "captured event timestamp moved after causal cutoff",
            "path": captured,
            "json": lambda data: [
                call["input"].update({"event_timestamp": "2026-09-15T09:25:00+00:00"})
                for call in data.get("calls", [])
                if call.get("run") == "run1"
            ],
        },
        {
            "id": "M18",
            "name": "proof mislabeled as direct-consumer-only",
            "path": ledger,
            "json": lambda data: data.update({"proof_type": "DIRECT_CONSUMER_ONLY_PROOF"}),
        },
    ]

    results: list[dict[str, Any]] = []
    detected = 0

    for mutation in mutations:
        path: Path = mutation["path"]
        original = path.read_text(encoding="utf-8")
        try:
            if "apply" in mutation:
                mutated = mutation["apply"](original)
                if mutated == original:
                    raise RuntimeError(f"{mutation['id']}:SOURCE_MUTATION_NO_EFFECT")
                path.write_text(mutated, encoding="utf-8")
            elif "json" in mutation:
                _mutate_json(path, mutation["json"])
            else:
                _mutate_jsonl(path, mutation["jsonl"])

            proc = _run_verifier(evidence_root)
            rejected = proc.returncode != 0
            if rejected:
                detected += 1
            results.append(
                {
                    "id": mutation["id"],
                    "name": mutation["name"],
                    "detected": rejected,
                    "verifier_returncode": proc.returncode,
                    "stderr_tail": proc.stderr[-1200:],
                    "stdout_tail": proc.stdout[-1200:],
                }
            )
            print(
                f"[{mutation['id']}] {mutation['name']}: "
                f"{'REJECTED_AS_EXPECTED' if rejected else 'SURVIVED_UNEXPECTEDLY'}"
            )
        finally:
            path.write_text(original, encoding="utf-8")

    final_baseline = _run_verifier(evidence_root)
    if final_baseline.returncode != 0:
        raise RuntimeError(
            f"POST_MUTATION_RESTORE_BASELINE_FAILED\n{final_baseline.stdout}\n{final_baseline.stderr}"
        )

    report = {
        "required_mutations": len(mutations),
        "detected": detected,
        "required_mutations_detected": f"{detected}/{len(mutations)}",
        "post_restore_baseline_pass": True,
        "results": results,
    }
    (evidence_root / "MUTATION_CAMPAIGN_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Mutation campaign complete: {detected}/{len(mutations)} detected.")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=None)
    args = parser.parse_args()
    short_sha = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(REPO_ROOT),
        text=True,
    ).strip()
    evidence_root = args.evidence_root or Path(
        f"/Volumes/TradeBotData/pr905-tradebuilder-canonical-proof-{short_sha}"
    )
    report = run_mutation_campaign(evidence_root)
    return 0 if report["detected"] == report["required_mutations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
