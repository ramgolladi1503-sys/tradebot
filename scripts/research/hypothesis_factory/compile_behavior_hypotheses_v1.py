#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

COMPILER_ID = "BEHAVIOR_HYPOTHESIS_COMPILER_V1"
ENGINE_ID = "BEHAVIOR_DISCOVERY_ENGINE_V2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def stable_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compile_passports(sequences: list[dict[str, object]], source_dataset_sha256: str, feature_schema_hash: str, search_family_id: str, max_candidates: int = 25) -> list[dict[str, object]]:
    passports = []
    for rank, seq in enumerate(sequences[:max_candidates], start=1):
        definition = {
            "state_sequence": seq["state_sequence"],
            "sequence_length": seq["sequence_length"],
            "minimum_episode_support_observed": seq["episode_support"],
            "minimum_distinct_session_support_observed": seq["distinct_session_support"],
        }
        passport = {
            "schema_version": 1,
            "candidate_id": f"BDE2_SEQ_{stable_hash(definition)[:16]}",
            "compiler_id": COMPILER_ID,
            "source_engine": ENGINE_ID,
            "source_dataset_sha256": source_dataset_sha256,
            "feature_schema_hash": feature_schema_hash,
            "causal_observability_contract": "candidate matches only after the final state in the frozen sequence is observable from same-session prefix data",
            "sequence_definition": definition,
            "matching_rule": "ordered contiguous state_sequence subsequence inside a causally built behavior episode",
            "minimum_support_rule": "support and distinct-session counts are measured before any outcome access; no forward labels used for selection",
            "direction": "UNKNOWN",
            "entry_concept": "NONE",
            "exit_concept": "NONE",
            "search_family_id": search_family_id,
            "search_pressure": {"candidate_rank_by_recurrence": rank, "candidate_count_compiled_in_batch": min(len(sequences), max_candidates), "source_sequence_records": len(sequences)},
            "runtime_authority": "NONE",
            "broker_actions_permitted": False,
            "edge_claimed": False,
            "forward_outcomes_used": False,
            "locked_outcomes_accessed": False,
            "next_action": "DEVELOPMENT_OUTCOME_TEST_ONLY_AFTER_GOVERNED_APPROVAL_AND_PARTITION_CHECK",
            "interpretation": "Frozen structural behavior hypothesis, not a strategy and not an edge claim.",
        }
        passport["passport_sha256"] = stable_hash({k: v for k, v in passport.items() if k != "passport_sha256"})
        passports.append(passport)
    return passports


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--sequences", required=True)
    ap.add_argument("--output-dir", default="research/strategy_certification/behavior_discovery_engine_v2/passports")
    ap.add_argument("--evidence-dir", default="research/evidence/behavior_discovery_engine_v2")
    ap.add_argument("--instrument", default="NIFTY")
    ap.add_argument("--source-dataset-sha256", required=True)
    ap.add_argument("--feature-schema-hash", required=True)
    ap.add_argument("--search-family-id", default="BDE2_SEQUENCE_FAMILY_V1")
    ap.add_argument("--max-candidates", type=int, default=25)
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    sp = Path(args.sequences)
    sp = sp if sp.is_absolute() else root / sp
    od = root / args.output_dir
    evd = root / args.evidence_dir
    od.mkdir(parents=True, exist_ok=True)
    evd.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "status": "FAIL_CLOSED", "compiler_id": COMPILER_ID, "runtime_authority": "NONE", "broker_actions_permitted": False, "edge_claimed": False, "forward_outcomes_used": False, "locked_outcomes_accessed": False}
    try:
        sequences = load_jsonl(sp)
        if any(s.get("forward_outcomes_used") for s in sequences):
            raise ValueError("sequence_input_contains_forward_outcomes")
        passports = compile_passports(sequences, args.source_dataset_sha256, args.feature_schema_hash, args.search_family_id, args.max_candidates)
        manifest = []
        for passport in passports:
            path = od / f"{passport['candidate_id']}.json"
            path.write_text(json.dumps(passport, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest.append({"candidate_id": passport["candidate_id"], "passport_path": str(path), "passport_file_sha256": sha256(path), "passport_sha256": passport["passport_sha256"]})
        manifest_path = evd / f"{args.instrument}_behavior_candidate_passport_manifest_v1.json"
        result.update({
            "status": "STRUCTURAL_CANDIDATE_PASSPORTS_FROZEN" if passports else "NO_STRUCTURAL_CANDIDATES_FROZEN",
            "sequences_path": str(sp),
            "sequences_sha256": sha256(sp),
            "sequence_records_read": len(sequences),
            "passports_frozen": len(passports),
            "source_dataset_sha256": args.source_dataset_sha256,
            "feature_schema_hash": args.feature_schema_hash,
            "search_family_id": args.search_family_id,
            "manifest": manifest,
            "next_action": "GOVERNED_DEVELOPMENT_OUTCOME_TEST" if passports else "REVIEW_DISCOVERY_SUPPORT_THRESHOLDS_WITHOUT_OUTCOME_PEEKING",
            "interpretation": "Candidate passports freeze recurrent causal structures only. Direction, entry, exit, and edge remain unknown.",
        })
        manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["manifest_path"] = str(manifest_path)
        result["manifest_sha256"] = sha256(manifest_path)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    summary = evd / f"{args.instrument}_behavior_candidate_passport_manifest_v1_summary.json"
    summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"STRUCTURAL_CANDIDATE_PASSPORTS_FROZEN", "NO_STRUCTURAL_CANDIDATES_FROZEN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
