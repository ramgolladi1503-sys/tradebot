from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .engine import EngineConfig, MarketStoryEngine
from .scenarios import build_scenario


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _terminal_decision(
    engine: MarketStoryEngine,
    kind: str,
    seed: int | None = None,
) -> dict[str, Any]:
    underlying, breadth, options = build_scenario(kind, noise_seed=seed)
    return engine.run(underlying, breadth, options).iloc[-1].to_dict()


def run_certification(
    output_dir: Path,
    noise_runs: int = 25,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = MarketStoryEngine()
    expected = {
        "bull": "BUY_CE",
        "bear": "BUY_PE",
        "false_break": "WAIT",
        "weak_breadth": "REJECT",
        "weak_option": "REJECT",
        "missing_option": "REJECT",
        "crossed_option": "REJECT",
    }
    baseline = {
        kind: _terminal_decision(engine, kind)
        for kind in expected
    }
    scenario_checks = {
        kind: baseline[kind]["decision"] == decision
        for kind, decision in expected.items()
    }

    noise_results: dict[str, Any] = {}
    for kind in ("bull", "bear"):
        decisions = [
            _terminal_decision(engine, kind, seed=index)["decision"]
            for index in range(noise_runs)
        ]
        target = expected[kind]
        noise_results[kind] = {
            "target": target,
            "runs": noise_runs,
            "stability": decisions.count(target) / len(decisions),
            "decisions": decisions,
        }

    underlying, breadth, options = build_scenario("bull")
    full = engine.run(underlying, breadth, options)
    prefix = engine.run(
        underlying.iloc[:-3],
        breadth.iloc[:-3],
        options.iloc[:-3],
    )
    full_prefix = full.iloc[: len(prefix)][
        ["decision", "state", "confidence"]
    ].reset_index(drop=True)
    prefix_values = prefix[
        ["decision", "state", "confidence"]
    ].reset_index(drop=True)
    prefix_invariance = full_prefix.equals(prefix_values)

    shifted = options.copy()
    shifted["timestamp"] = shifted["timestamp"] + pd.Timedelta(minutes=10)
    shifted_decision = engine.run(
        underlying,
        breadth,
        shifted,
    ).iloc[-1]["decision"]
    time_shift_control_pass = shifted_decision != "BUY_CE"

    deterministic_copy = {
        kind: _terminal_decision(engine, kind)
        for kind in expected
    }
    determinism_pass = canonical_hash(baseline) == canonical_hash(
        deterministic_copy
    )
    mirrored_symmetry = (
        baseline["bull"]["decision"] == "BUY_CE"
        and baseline["bear"]["decision"] == "BUY_PE"
    )
    all_pass = (
        all(scenario_checks.values())
        and all(
            result["stability"] >= 0.90
            for result in noise_results.values()
        )
        and prefix_invariance
        and time_shift_control_pass
        and determinism_pass
        and mirrored_symmetry
    )
    verdict = (
        "PASS_IMPLEMENTATION_ROBUSTNESS_GATE"
        if all_pass
        else "FAIL_IMPLEMENTATION_ROBUSTNESS_GATE"
    )
    payload = {
        "schema_version": "market_story_engine_v1.certification.1",
        "verdict": verdict,
        "claim_boundary": (
            "implementation robustness only; no profitable edge, option PnL, "
            "paper readiness, or live readiness certified"
        ),
        "config": asdict(EngineConfig()),
        "scenario_checks": scenario_checks,
        "baseline": baseline,
        "noise_results": noise_results,
        "prefix_invariance": prefix_invariance,
        "time_shift_control_pass": time_shift_control_pass,
        "shifted_terminal_decision": shifted_decision,
        "determinism_pass": determinism_pass,
        "mirrored_symmetry": mirrored_symmetry,
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    payload["semantic_sha256"] = canonical_hash(payload)
    path = output_dir / "certification.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = output_dir / "certification.json.sha256"
    sidecar.write_text(f"{digest}  certification.json\n")
    return payload
