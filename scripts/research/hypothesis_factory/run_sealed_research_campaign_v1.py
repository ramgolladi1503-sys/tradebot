#!/usr/bin/env python3
"""Minimal bounded controller for sealed strategy-research campaigns.

This controller orchestrates existing frozen generation scripts. It never invents
thresholds, rewrites passports, opens holdout without a declared stage, or grants
runtime/broker authority. Missing stage implementations fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_POLICY = "research/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1.json"
DEFAULT_LEDGER = "research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_LEDGER.jsonl"
DEFAULT_STATE = "research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_STATE.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as h:
        h.write(json.dumps(payload, sort_keys=True) + "\n")


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(root: Path, cmd: list[str]) -> int:
    print("[campaign] RUN", " ".join(cmd), flush=True)
    cp = subprocess.run(cmd, cwd=root, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    print(f"[campaign] EXIT {cp.returncode}", flush=True)
    return int(cp.returncode)


def count_configs(dev: dict[str, Any]) -> int:
    return sum(int(c.get("configs_tested", 0) or 0) for c in dev.get("candidates", []))


def nominated(dev: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in dev.get("candidates", []) if c.get("development_status") == "NOMINATED_FOR_VALIDATION" and c.get("nomination")]


def stage_descriptor(gen: dict[str, Any], stage: str) -> tuple[list[str] | None, str | None]:
    return gen.get(f"{stage}_command"), gen.get(f"{stage}_output")


def ensure_authority_none(payload: dict[str, Any], label: str) -> None:
    if payload.get("runtime_authority") != "NONE":
        raise ValueError(f"{label}:runtime_authority_not_none")
    if payload.get("broker_actions_permitted") is not False:
        raise ValueError(f"{label}:broker_actions_permitted")
    if payload.get("edge_claimed") is True:
        raise ValueError(f"{label}:premature_edge_claim")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    ap.add_argument("--ledger", default=DEFAULT_LEDGER)
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--max-steps", type=int, default=100)
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    policy_path = root / args.policy
    ledger_path = root / args.ledger
    state_path = root / args.state
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL_CLOSED",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "campaign_id": None,
        "policy_sha256": None,
        "generations_processed": 0,
        "total_frozen_configurations_tested": 0,
        "current_generation": None,
        "current_stage": None,
        "reason": None,
    }

    try:
        policy = read_json(policy_path)
        if policy.get("campaign_id") != "SEALED_RESEARCH_CAMPAIGN_V1":
            raise ValueError("campaign_id_mismatch")
        ensure_authority_none(policy, "policy")
        state["campaign_id"] = policy["campaign_id"]
        state["policy_sha256"] = sha256(policy_path)
        budget = policy["budget"]
        max_generations = int(budget["max_generations"])
        max_configs = int(budget["max_total_frozen_configurations"])
        registry = policy.get("generation_registry", [])
        if len(registry) > max_generations:
            raise ValueError("registered_generations_exceed_budget")

        steps = 0
        total_configs = 0
        processed = 0
        for gen in registry:
            if steps >= args.max_steps:
                state.update(status="FAIL_CLOSED", reason="MAX_STEPS_EXCEEDED")
                write_state(state_path, state)
                return 2
            gid = gen["generation_id"]
            freeze_path = root / gen["freeze_path"]
            if not freeze_path.exists():
                raise ValueError(f"{gid}:freeze_missing")
            freeze = read_json(freeze_path)
            ensure_authority_none(freeze, f"{gid}:freeze")
            if freeze.get("generation_id") != gid:
                raise ValueError(f"{gid}:freeze_id_mismatch")
            state.update(current_generation=gid, current_stage="development")
            write_state(state_path, state)

            dev_cmd, dev_out_rel = stage_descriptor(gen, "development")
            if not dev_cmd or not dev_out_rel:
                state.update(status="BLOCKED_MISSING_STAGE_IMPLEMENTATION", reason=f"{gid}:development_stage_missing")
                write_state(state_path, state)
                return 3
            dev_out = root / dev_out_rel
            if not dev_out.exists():
                rc = run_command(root, dev_cmd); steps += 1
                if rc != 0:
                    state.update(status="FAIL_CLOSED", reason=f"{gid}:development_exit_{rc}")
                    write_state(state_path, state)
                    return 2
            dev = read_json(dev_out)
            ensure_authority_none(dev, f"{gid}:development")
            if dev.get("status") != "DEVELOPMENT_SCREEN_COMPLETE":
                raise ValueError(f"{gid}:development_status_invalid")
            if dev.get("validation_accessed") is not False or dev.get("holdout_accessed") is not False:
                raise ValueError(f"{gid}:premature_reserved_data_access")
            ncfg = count_configs(dev)
            total_configs += ncfg
            if total_configs > max_configs:
                state.update(status="CAMPAIGN_EXHAUSTED_NO_EDGE", reason="CONFIGURATION_BUDGET_EXHAUSTED", total_frozen_configurations_tested=total_configs)
                write_state(state_path, state)
                append_jsonl(ledger_path, {"event":"CAMPAIGN_STOP","reason":state["reason"],"generation_id":gid,"total_configs":total_configs})
                return 0
            noms = nominated(dev)
            append_jsonl(ledger_path, {"event":"DEVELOPMENT_COMPLETE","generation_id":gid,"freeze_sha256":sha256(freeze_path),"development_output_sha256":sha256(dev_out),"configs_tested":ncfg,"nominated_count":len(noms)})

            if not noms:
                processed += 1
                append_jsonl(ledger_path, {"event":"GENERATION_CLOSED","generation_id":gid,"reason":"NO_DEVELOPMENT_SURVIVORS","holdout_accessed":False})
                continue

            val_cmd, val_out_rel = stage_descriptor(gen, "validation")
            if not val_cmd or not val_out_rel:
                state.update(status="BLOCKED_MISSING_STAGE_IMPLEMENTATION", reason=f"{gid}:validation_stage_missing", generations_processed=processed, total_frozen_configurations_tested=total_configs, current_stage="validation")
                write_state(state_path, state)
                append_jsonl(ledger_path, {"event":"BLOCKED","generation_id":gid,"stage":"validation","reason":"MISSING_PREDECLARED_STAGE_IMPLEMENTATION"})
                return 3
            val_out = root / val_out_rel
            if not val_out.exists():
                rc = run_command(root, val_cmd); steps += 1
                if rc != 0:
                    state.update(status="FAIL_CLOSED", reason=f"{gid}:validation_exit_{rc}")
                    write_state(state_path, state)
                    return 2
            val = read_json(val_out)
            ensure_authority_none(val, f"{gid}:validation")
            if val.get("holdout_outcomes_accessed") is not False:
                raise ValueError(f"{gid}:premature_holdout_access")
            advanced = list(val.get("advanced_passport_ids", []))
            append_jsonl(ledger_path, {"event":"VALIDATION_COMPLETE","generation_id":gid,"validation_output_sha256":sha256(val_out),"advanced_count":len(advanced)})
            if not advanced:
                processed += 1
                append_jsonl(ledger_path, {"event":"GENERATION_CLOSED","generation_id":gid,"reason":"NO_VALIDATION_SURVIVORS","holdout_accessed":False})
                continue

            for stage in ("robustness", "holdout", "certification"):
                cmd, out_rel = stage_descriptor(gen, stage)
                if not cmd or not out_rel:
                    state.update(status="BLOCKED_MISSING_STAGE_IMPLEMENTATION", reason=f"{gid}:{stage}_stage_missing", generations_processed=processed, total_frozen_configurations_tested=total_configs, current_stage=stage)
                    write_state(state_path, state)
                    append_jsonl(ledger_path, {"event":"BLOCKED","generation_id":gid,"stage":stage,"reason":"MISSING_PREDECLARED_STAGE_IMPLEMENTATION"})
                    return 3
                out = root / out_rel
                if not out.exists():
                    rc = run_command(root, cmd); steps += 1
                    if rc != 0:
                        state.update(status="FAIL_CLOSED", reason=f"{gid}:{stage}_exit_{rc}")
                        write_state(state_path, state)
                        return 2
                payload = read_json(out)
                ensure_authority_none(payload, f"{gid}:{stage}")
                append_jsonl(ledger_path, {"event":f"{stage.upper()}_COMPLETE","generation_id":gid,"output_sha256":sha256(out),"status":payload.get("status"),"verdict":payload.get("verdict")})
                if stage == "robustness" and payload.get("verdict") not in ("ROBUSTNESS_PASS", "PASS"):
                    processed += 1
                    append_jsonl(ledger_path, {"event":"GENERATION_CLOSED","generation_id":gid,"reason":"ROBUSTNESS_FAIL"})
                    break
                if stage == "holdout" and payload.get("verdict") not in ("HOLDOUT_PASS", "PASS"):
                    processed += 1
                    append_jsonl(ledger_path, {"event":"GENERATION_CLOSED","generation_id":gid,"reason":"HOLDOUT_FAIL"})
                    break
                if stage == "certification" and payload.get("verdict") in ("CERTIFIED", "STRUCTURAL_EDGE_CANDIDATE_FOUND"):
                    state.update(status="STRUCTURAL_EDGE_CANDIDATE_FOUND", reason="CERTIFICATION_STAGE_PASS", generations_processed=processed+1, total_frozen_configurations_tested=total_configs, current_stage="complete")
                    write_state(state_path, state)
                    return 0
            else:
                processed += 1

        state.update(status="CAMPAIGN_EXHAUSTED_NO_EDGE", reason="REGISTERED_GENERATIONS_EXHAUSTED", generations_processed=processed, total_frozen_configurations_tested=total_configs, current_generation=None, current_stage="complete")
        write_state(state_path, state)
        append_jsonl(ledger_path, {"event":"CAMPAIGN_STOP","reason":state["reason"],"generations_processed":processed,"total_configs":total_configs})
        return 0
    except Exception as e:
        state.update(status="FAIL_CLOSED", reason=f"{type(e).__name__}:{e}")
        write_state(state_path, state)
        print(json.dumps(state, indent=2), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
