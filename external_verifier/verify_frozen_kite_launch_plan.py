#!/usr/bin/env python3
"""Independent, standard-library-only verifier for the frozen Kite plan."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def verify(root: Path) -> dict:
    spec = root / "verification_spec"
    freeze = root / "launch_plan_freeze"
    if not freeze.is_dir():
        freeze = root / "fresh_preflight"
    plan = json.loads((freeze / "launch_plan.json").read_text())
    normalized_path = freeze / "launch_plan.normalized.json"
    if not normalized_path.is_file():
        normalized_path = freeze / "canonical_semantic_launch_plan.json"
    normalized = json.loads(normalized_path.read_text())
    snapshot = json.loads((freeze / "resolver_snapshot.json").read_text())
    allow = json.loads((spec / "semantic_field_allowlist.json").read_text())["fields"]
    required = json.loads((spec / "semantic_launch_plan_schema.json").read_text())["required"]
    rules = json.loads((spec / "instrument_classification_rules.json").read_text())
    authority = json.loads((spec / "authority_rules.json").read_text())
    binding = json.loads((spec / "campaign_binding_rules.json").read_text())
    if not (freeze / "FROZEN").is_file():
        raise ValueError("FAILED_GATE:FROZEN_MARKER_ABSENT")
    if not (root / "resolver_snapshot" / "SNAPSHOT_FROZEN").is_file():
        raise ValueError("FAILED_GATE:RESOLVER_SNAPSHOT_MARKER_ABSENT")
    if any(field not in normalized for field in required):
        raise ValueError("FAILED_GATE:SEMANTIC_FIELD_MISSING")
    unknown = sorted(set(normalized) - set(allow))
    if unknown:
        raise ValueError("FAILED_GATE:UNKNOWN_SEMANTIC_FIELD:" + ",".join(unknown))
    if plan.get("session_date") != binding["session_date"]:
        raise ValueError("FAILED_GATE:SESSION_DATE_MISMATCH")
    if plan.get("campaign_id") != binding["campaign_id"]:
        raise ValueError("FAILED_GATE:CAMPAIGN_ID_MISMATCH")
    for key, expected in authority.items():
        if key in plan and plan[key] != expected:
            raise ValueError("FAILED_GATE:EXECUTION_AUTHORITY_ENABLED")
    tokens = [int(x) for x in plan["final_union_tokens"]]
    observations = [int(x) for x in plan["observation_tokens"]]
    if tokens != [int(x) for x in normalized["final_union_tokens"]]:
        raise ValueError("FAILED_GATE:SEMANTIC_HASH_MISMATCH")
    if plan.get("subscription_modes") != normalized.get("subscription_modes"):
        raise ValueError("FAILED_GATE:SUBSCRIPTION_MODE_MISMATCH")
    if len(tokens) != len(set(tokens)):
        raise ValueError("FAILED_GATE:DUPLICATE_TOKEN")
    if len(tokens) != rules["total_count"] or len(observations) != rules["observation_count"]:
        raise ValueError("FAILED_GATE:TOKEN_COUNT_MISMATCH")
    if int(plan["configured_budget"]) > 150:
        raise ValueError("FAILED_GATE:TOKEN_BUDGET_EXCEEDED")
    if sorted(normalized["instruments"], key=lambda row: row["instrument_token"]) != normalized["instruments"]:
        raise ValueError("FAILED_GATE:INSTRUMENT_ORDER")
    semantic = dict(normalized)
    semantic.pop("resolver_snapshot_sha256", None)
    external_semantic = sha(semantic)
    expected_snapshot = sha(snapshot)
    if plan.get("resolver_snapshot_sha256") != expected_snapshot:
        raise ValueError("FAILED_GATE:RESOLVER_SNAPSHOT_HASH_MISMATCH")
    return {"verdict":"PASS_EXTERNAL_SEMANTIC_PLAN_VERIFICATION","semantic_sha256":external_semantic,"resolver_snapshot_sha256":expected_snapshot,"total_unique_tokens":len(tokens),"observation_tokens_present":len(observations),"additional_tokens":len(set(tokens)-set(observations)),"duplicates":0,"unknown_instruments":0,"budget":int(plan["configured_budget"]),"authority":authority,"campaign_id":binding["campaign_id"],"session_date":binding["session_date"],"no_websocket_started":True}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(Path(sys.argv[1]).resolve()), sort_keys=True, indent=2))
    except Exception as exc:
        print(json.dumps({"verdict":"REJECT","reason":str(exc)}, sort_keys=True))
        raise SystemExit(1)
